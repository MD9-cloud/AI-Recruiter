import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from server import ai, storage
from server.backup import backup
from server.main import app
from tests.control_data import JOBS, build


def login(client, username, password):
    response = client.post("/api/login", json={"login": username, "password": password})
    return {"Authorization": "Bearer " + response.json()["token"]}


class Acceptance(unittest.TestCase):
    def test_demo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "work.sqlite3"
            fixtures = root / "fixtures"
            manifest = build(fixtures)
            with patch.object(storage, "DB", database):
                with TestClient(app) as client:
                    self.assertEqual(client.get("/api/jobs").status_code, 401)
                    hr = login(client, "hr", "RecruiterDemo2026!")
                    admin = login(client, "admin", "RecruiterAdmin2026!")
                    self.assertEqual(client.get("/api/users", headers=hr).status_code, 403)
                    self.assertEqual(client.post("/api/users", headers=admin, json={
                        "login": "other", "password": "OtherDemoPass2026!", "role": "hr",
                    }).status_code, 200)
                    other = login(client, "other", "OtherDemoPass2026!")
                    entries = client.get("/api/knowledge", headers=hr).json()
                    self.assertEqual(len(entries), 5)
                    self.assertEqual(client.put("/api/knowledge/1", headers=hr, json={}).status_code, 403)
                    response = client.put("/api/knowledge/1", headers=admin, json={
                        "title": entries[0]["title"], "kind": entries[0]["kind"], "body": entries[0]["body"],
                    })
                    self.assertEqual(response.status_code, 200)
                    draft = client.post("/api/generate", headers=hr, json={
                        "role": "Разработчик", "level": "Junior", "ids": [1],
                    }).json()
                    self.assertEqual(draft["sources"], [{"id": 1, "version": 2}])
                    self.assertIn("[Укажите зарплату", draft["body"])
                    export = client.post("/api/docx", headers=hr, json={
                        "title": draft["title"], "body": draft["body"],
                    })
                    self.assertTrue(export.content.startswith(b"PK"))
                    for vacancy, terms in JOBS.items():
                        matches = [row for row in manifest if row[0] == vacancy]
                        job = {
                            "title": vacancy, "body": "\n".join(terms), "criteria": [],
                            "sources": draft["sources"],
                        }
                        job_id = client.post("/api/jobs", json=job, headers=hr).json()["id"]
                        route = f"/api/jobs/{job_id}"
                        self.assertEqual(client.get(route + "/candidates", headers=other).status_code, 404)
                        for sample in [name for _, name, _, _, _ in matches][:3]:
                            imported = client.post("/api/extract", headers=hr,
                                                   files={"file": (sample, (fixtures / sample).read_bytes())})
                            self.assertEqual(imported.status_code, 200)
                        uploads = client.post(route + "/candidates", headers=hr, files=[
                            ("files", (name, (fixtures / name).read_bytes()))
                            for name in [item[1] for item in matches] + ["broken.pdf", "no-text.pdf", "oversize.txt"]
                        ]).json()
                        self.assertEqual(sum("error" in row for row in uploads), 3)
                        ids = [row["id"] for row in uploads if "id" in row]
                        self.assertEqual(client.get(f"/api/candidates/{ids[0]}", headers=other).status_code, 404)
                        payload = {"ids": ids}
                        self.assertEqual(client.post(route + "/analyze", headers=hr, json=payload).status_code, 422)
                        job["criteria"] = client.post("/api/suggest", headers=hr, json={"body": job["body"]}).json()
                        job["criteria"][1].update(weight=1, required=False)
                        self.assertEqual(client.put(route, headers=hr, json=job).status_code, 200)
                        candidate_path = f"/api/candidates/{ids[0]}"
                        decision = {"decision": "Требует уточнения", "note": "Проверить проект"}
                        self.assertEqual(client.put(candidate_path + "/decision", headers=hr, json=decision).status_code, 200)
                        for _ in range(2):
                            self.assertEqual(client.post(route + "/analyze", headers=hr, json=payload).status_code, 200)
                        deadline = time.monotonic() + 10
                        while True:
                            rows = client.get(route + "/candidates", headers=hr).json()
                            if all(row["status"] == "done" for row in rows):
                                break
                            self.assertLess(time.monotonic(), deadline, rows)
                            time.sleep(.03)
                        expected = {name: score for _, name, _, _, score in matches}
                        self.assertEqual({r["filename"]: round(r["score"]) for r in rows}, expected)
                        record = client.get(candidate_path, headers=hr).json()
                        self.assertEqual(record["decision"], decision["decision"])
                        self.assertEqual(len(record["history"]), 1)
                        self.assertEqual(client.put(candidate_path, headers=hr, json={
                            "name": record["name"], "body": record["body"] + "\nEdited",
                        }).status_code, 200)
                        job["body"] += "\nEdited"
                        client.put(route, headers=hr, json=job)
                        self.assertTrue(all(row["status"] == "stale" for row in client.get(route + "/candidates", headers=hr).json()))
                with patch("server.backup.DB", database):
                    snapshot = backup(root / "backups")
                with patch.object(storage, "DB", snapshot):
                    with TestClient(app) as client:
                        self.assertEqual(len(client.get("/api/jobs", headers=hr).json()), 2)
                        self.assertEqual(client.delete(candidate_path, headers=hr).status_code, 200)
                        self.assertEqual(client.get(candidate_path, headers=hr).status_code, 404)

    def test_weighting_and_evidence(self):
        criteria = [{"text": text, "weight": weight, "required": weight == 2}
                    for text, weight in zip(["Python", "SQL", "Docker"], [2, 2, 1])]
        response = {
            "criteria": [
                {"id": 1, "status": "подтверждено", "reason": "Разработка", "quote": "Python API"},
                {"id": 2, "status": "частично подтверждено", "reason": "Только курс", "quote": "курс SQL"},
                {"id": 3, "status": "не подтверждено", "reason": "Нет подтверждения", "quote": ""},
            ], "matches": [], "gaps": [], "questions": [], "summary": "Результат по резюме.",
        }
        resume = "Email: fictional@example.org\nPython API, курс SQL"
        with patch.object(ai, "DEMO", False), patch.object(ai, "ask", return_value=response) as provider:
            score, _ = asyncio.run(ai.analyze(criteria, resume))
            self.assertEqual(score, 60)
            self.assertNotIn("fictional@example.org", provider.call_args.args[1]["resume"])
            response["criteria"][0]["quote"] = "несуществующая цитата"
            with self.assertRaises(ai.AIError):
                asyncio.run(ai.analyze(criteria, resume))
