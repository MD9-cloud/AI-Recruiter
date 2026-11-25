import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.getenv("RECRUITER_DB", ROOT / "data" / "recruiter.sqlite3"))
DEMO = os.getenv("RECRUITER_DEMO", "1") == "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, login TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('hr','admin'))
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
    expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
    body TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY, owner INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS job_versions (
    job_id INTEGER NOT NULL REFERENCES jobs ON DELETE CASCADE, version INTEGER NOT NULL,
    title TEXT NOT NULL, body TEXT NOT NULL, criteria TEXT NOT NULL,
    sources TEXT NOT NULL, PRIMARY KEY(job_id,version)
);
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs ON DELETE CASCADE,
    name TEXT NOT NULL, filename TEXT NOT NULL, original BLOB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    decision TEXT NOT NULL DEFAULT 'Не рассмотрен', note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS resume_versions (
    candidate_id INTEGER NOT NULL REFERENCES candidates ON DELETE CASCADE,
    version INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(candidate_id,version)
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES candidates ON DELETE CASCADE,
    job_version INTEGER NOT NULL, resume_version INTEGER NOT NULL,
    status TEXT NOT NULL, score REAL, result TEXT, error TEXT, model TEXT,
    prompt_version TEXT, updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(candidate_id,job_version,resume_version)
);
CREATE TABLE IF NOT EXISTS demo_analyses (
    id TEXT PRIMARY KEY NOT NULL,
    result TEXT NOT NULL
);
"""

SEED = [
    ("Backend-разработчик", "Роль", "Разработка HTTP API. Python, FastAPI, SQL, тестирование."),
    ("Frontend-разработчик", "Роль", "Веб-интерфейсы на Flutter и Dart. Доступность интерфейсов."),
    ("Инженер по тестированию", "Роль", "Функциональные проверки, тест-дизайн, API и отчёты об ошибках."),
    ("Портал заказов", "Проект", "Внутренний портал заказов. Команда поддерживает API и веб-клиент."),
    ("Контроль качества", "Задача", "Проверка изменений, ревью кода, автоматизация регрессионных тестов."),
]

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"{salt}:{digest.hex()}"


def initialize():
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        if not any(column["name"] == "owner_id" for column in db.execute("PRAGMA table_info(demo_analyses)")):
            db.execute("ALTER TABLE demo_analyses ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        db.execute("CREATE INDEX IF NOT EXISTS demo_analyses_owner ON demo_analyses(owner_id)")
        db.execute("UPDATE analyses SET status='error',error='Сервер перезапустился. Повторите анализ.' WHERE status IN ('queued','running')")
        db.execute("DELETE FROM sessions WHERE expires <= unixepoch()")
        if not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            if DEMO:
                for login, password, role in [
                    ("hr", "RecruiterDemo2026!", "hr"), ("admin", "RecruiterAdmin2026!", "admin")
                ]:
                    db.execute("INSERT INTO users(login,password,role) VALUES(?,?,?)", (login, hash_password(password), role))
                db.executemany("INSERT INTO knowledge(title,kind,body) VALUES(?,?,?)", SEED)
            else:
                password = os.getenv("RECRUITER_ADMIN_PASSWORD", "")
                if len(password) < 12:
                    raise RuntimeError("Укажите RECRUITER_ADMIN_PASSWORD длиной от 12 символов.")
                db.execute("INSERT INTO users(login,password,role) VALUES('admin',?,'admin')", (hash_password(password),))
