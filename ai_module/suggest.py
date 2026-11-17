from . import config, prompts, stub
from .client import complete_json
from .errors import AIModuleError

MAX_CRITERIA = 15


def suggest_criteria(vacancy_text: str, *, transport=None) -> list[dict]:
    if not isinstance(vacancy_text, str) or not vacancy_text.strip():
        raise AIModuleError("bad_input", "Введите текст вакансии.")
    settings = config.load()
    if settings.mode == "stub":
        raw = stub.suggest(vacancy_text)
    else:
        reply = complete_json(settings, [{"role": "system", "content": prompts.SUGGEST},
                                         {"role": "user", "content": prompts.tag("vacancy", vacancy_text)}],
                              transport=transport)
        raw = reply.get("criteria")
        if not isinstance(raw, list):
            raise AIModuleError("bad_response", "ИИ вернул некорректный список критериев.")

    result, seen = [], set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        text = item["text"].strip()[:500]
        if not text or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        required = item.get("required") is not False
        result.append({"id": f"c{len(result) + 1}", "text": text, "required": required,
                       "weight": 2 if required else 1})
        if len(result) == MAX_CRITERIA:
            break
    if not result:
        raise AIModuleError("bad_response", "Не удалось выделить критерии из вакансии.")
    return result
