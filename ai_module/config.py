import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-flash"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


@dataclass(frozen=True)
class Settings:
    mode: str
    url: str
    model: str
    key: str
    timeout: float


def _env_file() -> dict[str, str]:
    values = {}
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip("'\"")
    return values


def load() -> Settings:
    file = _env_file()

    def get(name, default=""):
        return os.environ.get(name) or file.get(name) or default

    key = get("RECRUITER_AI_KEY")
    mode = get("RECRUITER_AI_MODE", "live" if key else "stub").lower()
    if mode not in ("stub", "live"):
        mode = "stub"
    try:
        timeout = min(120.0, max(1.0, float(get("RECRUITER_AI_TIMEOUT", "60"))))
    except ValueError:
        timeout = 60.0
    return Settings(mode=mode, url=get("RECRUITER_AI_URL", DEFAULT_URL),
                    model=get("RECRUITER_AI_MODEL", DEFAULT_MODEL), key=key, timeout=timeout)
