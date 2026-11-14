import asyncio
import hmac
import json
import os
import secrets
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import ai
from .demo_analysis import router as demo_analysis_router
from .files import MAX_BYTES, MAX_TEXT, extract, make_docx
from .storage import DEMO, ROOT, connect, hash_password, initialize

DECISIONS = Literal["Не рассмотрен", "Пригласить", "Отказать", "Требует уточнения"]


def not_found():
    raise HTTPException(404, "Запись не найдена.")


def job_for(db, job_id, user):
    row = db.execute(
        "SELECT j.*,v.title,v.body,v.criteria,v.sources FROM jobs j JOIN job_versions v "
        "ON j.id=v.job_id AND j.version=v.version WHERE j.id=? AND j.owner=?", (job_id, user["id"])
    ).fetchone()
    return row or not_found()


def candidate_for(db, candidate_id, user):
    row = db.execute(
        "SELECT c.id,c.job_id,c.name,c.filename,c.version,c.decision,c.note,r.body,j.version AS job_version "
        "FROM candidates c JOIN jobs j ON j.id=c.job_id JOIN resume_versions r ON "
        "r.candidate_id=c.id AND r.version=c.version WHERE c.id=? AND j.owner=?", (candidate_id, user["id"])
    ).fetchone()
    return row or not_found()


def job_json(row):
    data = dict(row)
    for key in ("criteria", "sources"):
        data[key] = json.loads(data[key])
    return data


def result_json(row):
    data = dict(row)
    data["result"] = json.loads(data["result"]) if data["result"] else None
    return data


async def worker(wake):
    while True:
        wake.clear()
        with connect() as db:
            task = db.execute(
                "SELECT a.id,v.criteria,r.body FROM analyses a JOIN candidates c ON c.id=a.candidate_id "
                "JOIN job_versions v ON v.job_id=c.job_id AND v.version=a.job_version "
                "JOIN resume_versions r ON r.candidate_id=c.id AND r.version=a.resume_version "
                "WHERE a.status='queued' ORDER BY a.id LIMIT 1"
            ).fetchone()
            if task:
                db.execute("UPDATE analyses SET status='running',updated=CURRENT_TIMESTAMP WHERE id=?", (task["id"],))
        if task is None:
            await wake.wait()
            continue
        try:
            score, result = await ai.analyze(json.loads(task["criteria"]), task["body"])
            with connect() as db:
                db.execute("UPDATE analyses SET status='done',score=?,result=?,updated=CURRENT_TIMESTAMP WHERE id=?",
                           (score, json.dumps(result, ensure_ascii=False), task["id"]))
        except Exception as exc:
            message = str(exc) if isinstance(exc, ai.AIError) else "Анализ прерван. Повторите попытку."
            with connect() as db:
                db.execute("UPDATE analyses SET status='error',error=?,updated=CURRENT_TIMESTAMP WHERE id=?", (message, task["id"]))


@asynccontextmanager
async def lifespan(app):
    initialize()
    app.state.wake = asyncio.Event()
    task = asyncio.create_task(worker(app.state.wake))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="ИИ-Рекрутер", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:53144"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
bearer = HTTPBearer(auto_error=False)


def token_hash(token):
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials:
        with connect() as db:
            row = db.execute(
                "SELECT u.id,u.login,u.role FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token=? AND s.expires>unixepoch()", (token_hash(credentials.credentials),)
            ).fetchone()
            if row:
                return dict(row)
    raise HTTPException(401, "Войдите в приложение.")


def hr(user: Annotated[dict, Depends(current_user)]):
    if user["role"] != "hr":
        raise HTTPException(403, "Действие доступно HR-специалисту.")
    return user


def admin(user: Annotated[dict, Depends(current_user)]):
    if user["role"] != "admin":
        raise HTTPException(403, "Действие доступно администратору.")
    return user


User = Annotated[dict, Depends(current_user)]
HR = Annotated[dict, Depends(hr)]
Admin = Annotated[dict, Depends(admin)]


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Login(Input):
    login: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class Account(Login):
    password: str = Field(min_length=12, max_length=256)
    role: Literal["hr", "admin"] = "hr"


class Body(Input):
    body: str = Field(min_length=1, max_length=MAX_TEXT)


class Draft(Body):
    title: str = Field(min_length=1, max_length=200)


class Source(Input):
    id: int
    version: int


class Job(Draft):
    criteria: list[ai.Criterion] = Field(max_length=50)
    sources: list[Source] = Field(default_factory=list, max_length=30)


class Resume(Body):
    name: str = Field(min_length=1, max_length=200)


class Decision(Input):
    decision: DECISIONS
    note: str = Field(default="", max_length=3000)


class Batch(Input):
    ids: list[int] = Field(min_length=1, max_length=20)
    consent: bool = False


class Entry(Draft):
    kind: Literal["Роль", "Задача", "Навык", "Технология", "Проект", "Квалификация"]


class Generation(Input):
    role: str = Field(min_length=1, max_length=200)
    level: str = Field(min_length=1, max_length=100)
    ids: list[int] = Field(min_length=1, max_length=30)
    extra: str = Field(default="", max_length=4000)


@app.get("/api/info")
def info():
    return {"demo": DEMO, "model": ai.MODEL, "version": app.version}


@app.post("/api/login")
def login(payload: Login):
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE login=?", (payload.login,)).fetchone()
        stored = user["password"] if user else "0" * 32 + ":" + "0" * 128
        salt = stored.split(":")[0]
        if not hmac.compare_digest(hash_password(payload.password, salt), stored) or not user:
            raise HTTPException(401, "Проверьте логин и пароль.")
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES(?,?,unixepoch()+43200)", (token_hash(token), user["id"]))
        return {"token": token, "login": user["login"], "role": user["role"]}


@app.post("/api/logout")
def logout(user: User, credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]):
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE token=?", (token_hash(credentials.credentials),))
    return {}


@app.get("/api/users")
def users(user: Admin):
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT id,login,role FROM users ORDER BY login")]


@app.post("/api/users")
def create_user(payload: Account, user: Admin):
    with connect() as db:
        cursor = db.execute("INSERT OR IGNORE INTO users(login,password,role) VALUES(?,?,?)",
                            (payload.login, hash_password(payload.password), payload.role))
        if not cursor.rowcount:
            raise HTTPException(409, "Этот логин уже используется.")
        return {"id": cursor.lastrowid}


@app.delete("/api/users/{user_id}")
def remove_user(user_id: int, user: Admin):
    if user_id == user["id"]:
        raise HTTPException(409, "Удалить текущую учётную запись нельзя.")
    with connect() as db:
        if not db.execute("DELETE FROM users WHERE id=?", (user_id,)).rowcount:
            not_found()
    return {}


@app.get("/api/knowledge")
def knowledge(user: User):
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM knowledge ORDER BY id")]


@app.post("/api/knowledge")
def create_entry(payload: Entry, user: Admin):
    with connect() as db:
        cursor = db.execute("INSERT INTO knowledge(title,kind,body) VALUES(?,?,?)", (payload.title, payload.kind, payload.body))
        return {"id": cursor.lastrowid}


@app.put("/api/knowledge/{entry_id}")
def update_entry(entry_id: int, payload: Entry, user: Admin):
    with connect() as db:
        cursor = db.execute("UPDATE knowledge SET title=?,kind=?,body=?,version=version+1 WHERE id=?",
                            (payload.title, payload.kind, payload.body, entry_id))
        if not cursor.rowcount:
            not_found()
    return {}


@app.delete("/api/knowledge/{entry_id}")
def delete_entry(entry_id: int, user: Admin):
    with connect() as db:
        if not db.execute("DELETE FROM knowledge WHERE id=?", (entry_id,)).rowcount:
            not_found()
    return {}


@app.post("/api/generate")
async def generate(payload: Generation, user: HR):
    with connect() as db:
        entries = []
        for entry_id in dict.fromkeys(payload.ids):
            row = db.execute("SELECT * FROM knowledge WHERE id=?", (entry_id,)).fetchone()
            entries.append(dict(row or not_found()))
    try:
        return await ai.generate(payload.role, payload.level, entries, payload.extra)
    except ai.AIError as exc:
        raise HTTPException(502, str(exc)) from None


@app.post("/api/docx")
def docx(payload: Draft, user: HR):
    return Response(make_docx(payload.title, payload.body),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.post("/api/suggest")
async def suggest(payload: Body, user: HR):
    try:
        return await ai.suggest(payload.body)
    except ai.AIError as exc:
        raise HTTPException(502, str(exc)) from None


def read_upload(upload):
    name = Path((upload.filename or "файл").replace("\\", "/")).name
    raw = upload.file.read(MAX_BYTES + 1)
    return name, raw, extract(name, raw)


@app.post("/api/extract")
def extract_job(user: HR, file: Annotated[UploadFile, File()]):
    try:
        name, _, body = read_upload(file)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"filename": name, "body": body}


@app.get("/api/jobs")
def jobs(user: HR):
    with connect() as db:
        return [job_json(row) for row in db.execute(
            "SELECT j.id,j.version,v.title,v.body,v.criteria,v.sources,"
            "(SELECT count(*) FROM candidates c WHERE c.job_id=j.id) AS count "
            "FROM jobs j JOIN job_versions v ON j.id=v.job_id AND j.version=v.version "
            "WHERE j.owner=? ORDER BY j.id DESC", (user["id"],)
        )]


def save_version(db, job_id, version, payload):
    db.execute("INSERT INTO job_versions VALUES(?,?,?,?,?,?)",
               (job_id, version, payload.title, payload.body,
                json.dumps([item.model_dump() for item in payload.criteria], ensure_ascii=False),
                json.dumps([item.model_dump() for item in payload.sources])))


@app.post("/api/jobs")
def create_job(payload: Job, user: HR):
    with connect() as db:
        cursor = db.execute("INSERT INTO jobs(owner) VALUES(?)", (user["id"],))
        save_version(db, cursor.lastrowid, 1, payload)
        return {"id": cursor.lastrowid}


@app.put("/api/jobs/{job_id}")
def update_job(job_id: int, payload: Job, user: HR):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = job_json(job_for(db, job_id, user))
        if any(previous[key] != value for key, value in payload.model_dump().items()):
            version = previous["version"] + 1
            save_version(db, job_id, version, payload)
            db.execute("UPDATE jobs SET version=? WHERE id=?", (version, job_id))
    return {}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, user: HR):
    with connect() as db:
        if not db.execute("DELETE FROM jobs WHERE id=? AND owner=?", (job_id, user["id"])).rowcount:
            not_found()
    return {}


@app.get("/api/jobs/{job_id}/candidates")
def candidates(job_id: int, user: HR):
    with connect() as db:
        job_for(db, job_id, user)
        return [dict(row) for row in db.execute(
            "SELECT c.id,c.name,c.filename,c.version,c.decision,c.note,a.score,a.error,a.model,"
            "CASE WHEN a.id IS NOT NULL THEN a.status WHEN EXISTS(SELECT 1 FROM analyses h WHERE h.candidate_id=c.id) "
            "THEN 'stale' ELSE 'new' END AS status, a.result "
            "FROM candidates c JOIN jobs j ON j.id=c.job_id LEFT JOIN analyses a ON a.candidate_id=c.id "
            "AND a.job_version=j.version AND a.resume_version=c.version WHERE j.id=? ORDER BY c.id DESC", (job_id,)
        )]


@app.post("/api/jobs/{job_id}/candidates")
def upload(job_id: int, user: HR, files: Annotated[list[UploadFile], File()]):
    if not 1 <= len(files) <= 20:
        raise HTTPException(422, "Загрузите от 1 до 20 резюме за раз.")
    with connect() as db:
        job_for(db, job_id, user)
    items = []
    for file in files:
        try:
            name, raw, body = read_upload(file)
        except ValueError as exc:
            items.append({"filename": file.filename, "error": str(exc)})
            continue
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job_for(db, job_id, user)
            cursor = db.execute("INSERT INTO candidates(job_id,name,filename,original) VALUES(?,?,?,?)",
                                (job_id, Path(name).stem[:200] or "Кандидат", name, raw))
            db.execute("INSERT INTO resume_versions VALUES(?,1,?)", (cursor.lastrowid, body))
            items.append({"filename": name, "id": cursor.lastrowid})
    return items


@app.get("/api/candidates/{candidate_id}")
def candidate(candidate_id: int, user: HR):
    with connect() as db:
        row = candidate_for(db, candidate_id, user)
        analyses = db.execute("SELECT * FROM analyses WHERE candidate_id=? ORDER BY id DESC", (candidate_id,))
        return {**dict(row), "history": [result_json(item) for item in analyses]}


@app.put("/api/candidates/{candidate_id}")
def update_candidate(candidate_id: int, payload: Resume, user: HR):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = candidate_for(db, candidate_id, user)
        version = previous["version"]
        if payload.body != previous["body"]:
            version += 1
            db.execute("INSERT INTO resume_versions VALUES(?,?,?)", (candidate_id, version, payload.body))
        db.execute("UPDATE candidates SET name=?,version=? WHERE id=?", (payload.name, version, candidate_id))
    return {}


@app.put("/api/candidates/{candidate_id}/decision")
def decide(candidate_id: int, payload: Decision, user: HR):
    with connect() as db:
        candidate_for(db, candidate_id, user)
        db.execute("UPDATE candidates SET decision=?,note=? WHERE id=?", (payload.decision, payload.note, candidate_id))
    return {}


@app.delete("/api/candidates/{candidate_id}")
def delete_candidate(candidate_id: int, user: HR):
    with connect() as db:
        candidate_for(db, candidate_id, user)
        db.execute("DELETE FROM candidates WHERE id=?", (candidate_id,))
    return {}


@app.post("/api/jobs/{job_id}/analyze")
async def enqueue(job_id: int, payload: Batch, user: HR, request: Request):
    if not DEMO and not payload.consent:
        raise HTTPException(422, "Подтвердите передачу текста внешнему ИИ.")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = job_for(db, job_id, user)
        if not json.loads(job["criteria"]):
            raise HTTPException(422, "Добавьте и сохраните подтверждённые критерии вакансии.")
        for candidate_id in dict.fromkeys(payload.ids):
            row = candidate_for(db, candidate_id, user)
            if row["job_id"] != job_id:
                not_found()
            db.execute(
                "INSERT INTO analyses(candidate_id,job_version,resume_version,status,model,prompt_version) "
                "VALUES(?,?,?,'queued',?,?) ON CONFLICT(candidate_id,job_version,resume_version) "
                "DO UPDATE SET status='queued',error=NULL,model=excluded.model,prompt_version=excluded.prompt_version,"
                "updated=CURRENT_TIMESTAMP WHERE analyses.status='error'",
                (candidate_id, job["version"], row["version"], ai.MODEL, ai.TEMPLATE)
            )
    request.app.state.wake.set()
    return {}


if DEMO:
    app.include_router(demo_analysis_router)

web = Path(os.getenv("RECRUITER_WEB", ROOT / "client" / "build" / "web"))
if (web / "index.html").is_file():
    app.mount("/", StaticFiles(directory=web, html=True), name="web")
