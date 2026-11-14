import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from server import demo_analysis, storage
from server.main import app

PATH = "/api/demo/analyses"
CONTROL = {
    "vacancy_text": "Ищем Python-разработчика.",
    "resume_text": "Год писал на Python. Прошёл учебный курс по FastAPI",
    "criteria": [
        {"id": "c1", "text": "знает Python", "required": True},
        {"id": "c2", "text": "разрабатывал API на FastAPI", "required": True},
        {"id": "c3", "text": "работал с Docker", "required": False},
    ],
}


class DemoAnalysis(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(storage, "DB", Path(directory) / "test.sqlite3"))
        self.payload = copy.deepcopy(CONTROL)

    def test_score_and_reopen(self):
        with TestClient(app) as client:
            response = client.post(PATH, json=self.payload)
            self.assertEqual(response.status_code, 201, response.text)
            saved = response.json()
            self.assertEqual(saved["score_percent"], 60)
            self.assertEqual([item["weight"] for item in saved["criteria"]], [2, 2, 1])
            self.assertEqual([item["status"] for item in saved["criteria_results"]],
                             ["confirmed", "partial", "unconfirmed"])
            self.assertEqual(saved["unconfirmed_required"], [])
        with TestClient(app) as client:
            reopened = client.get(f"{PATH}/{saved['analysis_id']}")
            self.assertEqual(reopened.status_code, 200)
            self.assertEqual(reopened.json(), saved)
            self.assertEqual(client.get(f"{PATH}/00000000-0000-0000-0000-000000000000").status_code, 404)

    def test_explicit_weights_and_required_gap(self):
        self.payload["criteria"][2].update(required=True, weight=4)
        with TestClient(app) as client:
            response = client.post(PATH, json=self.payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["score_percent"], 37.5)
        self.assertEqual(response.json()["unconfirmed_required"], [self.payload["criteria"][2]])

    def test_bad_input_does_not_call_provider(self):
        with TestClient(app) as client, patch.object(demo_analysis, "fixed_provider") as provider:
            for criteria in ([], [self.payload["criteria"][0]] * 2):
                response = client.post(PATH, json={**self.payload, "criteria": criteria})
                self.assertEqual(response.status_code, 422, response.text)
            for field, value in (("weight", 0), ("weight", 6), ("weight", 1.5), ("weight", True),
                                 ("weight", "2"), ("required", None)):
                with self.subTest(field=field, value=value):
                    criteria = [{**self.payload["criteria"][0], field: value}]
                    response = client.post(PATH, json={**self.payload, "criteria": criteria})
                    self.assertEqual(response.status_code, 422, response.text)
            provider.assert_not_called()

    def test_bad_provider_output_is_rejected_and_not_saved(self):
        payload = demo_analysis.AnalysisInput.model_validate(self.payload)
        reply = demo_analysis.fixed_provider(payload.criteria, payload.resume_text)
        with TestClient(app) as client:
            for index, changes in (
                (0, {"criterion_id": "c2"}),
                (0, {"criterion_id": "c4"}),
                (0, {"status": "unknown"}),
                (0, {"quote": "цитата вне резюме"}),
                (1, {"quote": None}),
                (2, {"quote": ""}),
            ):
                with self.subTest(changes=changes):
                    invalid = copy.deepcopy(reply)
                    invalid["criteria_results"][index].update(changes)
                    with patch.object(demo_analysis, "fixed_provider", return_value=invalid):
                        response = client.post(PATH, json=self.payload)
                    self.assertEqual(response.status_code, 502, response.text)
                    self.assertNotIn("score_percent", response.json())
            with storage.connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM demo_analyses").fetchone()[0], 0)
