import json
import sys

from . import AIModuleError, analyze_resume, draft_vacancy, load_settings, suggest_criteria
from .stub import CONTROL_RESUME

CRITERIA = [
    {"id": "c1", "text": "знает Python", "required": True, "weight": 2},
    {"id": "c2", "text": "разрабатывал API на FastAPI", "required": True, "weight": 2},
    {"id": "c3", "text": "работал с Docker", "required": False, "weight": 1},
]
VACANCY = "Ищем Python-разработчика. Нужен опыт разработки API на FastAPI и SQL. Docker будет плюсом."


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    settings = load_settings()
    print(f"Режим: {settings.mode}" + (f", модель {settings.model}" if settings.mode == "live" else ""),
          file=sys.stderr)
    try:
        if command == "analyze":
            result = analyze_resume(CRITERIA, CONTROL_RESUME, VACANCY)
        elif command == "suggest":
            result = suggest_criteria(VACANCY)
        elif command == "draft":
            result = draft_vacancy("Python-разработчик", [
                {"id": 1, "body": "Отдел backend разрабатывает API для мобильного приложения банка."},
                {"id": 2, "body": "Стек: Python, FastAPI, PostgreSQL, Docker. Код-ревью обязательно."},
            ], level="Junior")
        else:
            sys.exit("Команды: analyze, suggest, draft")
    except AIModuleError as exc:
        sys.exit(f"Ошибка ({exc.kind}): {exc.message}")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


main()
