import json

from . import config, prompts, stub
from .client import complete_json
from .errors import AIModuleError

PLACEHOLDERS = {"salary": "[Укажите зарплату]", "schedule": "[Укажите график работы]",
                "format": "[Укажите формат работы: офис / удалённо / гибрид]"}
LISTS = ("responsibilities", "required", "preferred")


def draft_vacancy(role: str, knowledge: list, extra: str | None = None, level: str | None = None,
                  *, transport=None) -> dict:
    if not isinstance(role, str) or not role.strip():
        raise AIModuleError("bad_input", "Укажите должность.")
    entries = []
    for entry in knowledge or []:
        entry = {"body": entry} if isinstance(entry, str) else dict(entry)
        if isinstance(entry.get("body"), str) and entry["body"].strip():
            entries.append(entry)
    if not entries:
        raise AIModuleError("bad_input", "Выберите хотя бы одну запись базы знаний отдела.")

    settings = config.load()
    title = f"{role.strip()}{', ' + level.strip() if level and level.strip() else ''}"
    if settings.mode == "stub":
        data = stub.draft(title, entries, extra)
    else:
        knowledge_text = "\n\n".join(prompts.tag("entry", e["body"]) for e in entries)
        user = (json.dumps({"role": role, "level": level}, ensure_ascii=False) + "\n\n" + knowledge_text
                + ("\n\n" + prompts.tag("hr_notes", extra) if extra else ""))
        data = complete_json(settings, [{"role": "system", "content": prompts.DRAFT},
                                        {"role": "user", "content": user}], transport=transport)

    def strings(value):
        return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []

    conditions = data.get("conditions") if isinstance(data.get("conditions"), dict) else {}
    result = {"title": str(data.get("title") or title).strip()[:200],
              "department": str(data.get("department") or "").strip(),
              **{name: strings(data.get(name)) for name in LISTS},
              "conditions": {name: (str(conditions[name]).strip() if conditions.get(name) else placeholder)
                             for name, placeholder in PLACEHOLDERS.items()}
              | {"other": strings(conditions.get("other"))},
              "sources": [e["id"] for e in entries if "id" in e]}
    if not result["responsibilities"] and not result["required"] and not result["department"]:
        raise AIModuleError("bad_response", "ИИ вернул пустой черновик вакансии.")
    return result


def draft_to_text(draft: dict) -> str:
    def section(name, items):
        return f"{name}\n" + "\n".join(f"• {item}" for item in items) if items else ""

    c = draft["conditions"]
    parts = [draft["title"], draft["department"],
             section("Обязанности", draft["responsibilities"]),
             section("Обязательные требования", draft["required"]),
             section("Желательные требования", draft["preferred"]),
             section("Условия работы", [f"Зарплата: {c['salary']}", f"График: {c['schedule']}",
                                        f"Формат: {c['format']}", *c["other"]])]
    return "\n\n".join(part for part in parts if part)
