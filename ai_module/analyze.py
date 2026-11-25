import json
import re

from . import config, prompts, stub
from .client import complete_json
from .criteria import normalize
from .errors import AIModuleError

STATUSES = ("confirmed", "partial", "unconfirmed")
OUTER_QUOTES = "\"'«»“”„ "


def analyze_resume(criteria, resume_text: str, vacancy_text: str | None = None, *, transport=None, sleep=None):
    items = normalize(criteria)
    if not isinstance(resume_text, str) or not resume_text.strip():
        raise AIModuleError("bad_input", "Введите текст резюме.")
    settings = config.load()
    if settings.mode == "stub":
        return stub.analyze(items, resume_text)

    data = {"criteria": [{"criterion_id": i["id"], "text": i["text"], "required": i["required"]} for i in items]}
    user = json.dumps(data, ensure_ascii=False) + "\n\n" + prompts.tag("resume", resume_text)
    if vacancy_text and vacancy_text.strip():
        user += "\n\n" + prompts.tag("vacancy", vacancy_text)
    messages = [{"role": "system", "content": prompts.ANALYZE}, {"role": "user", "content": user}]
    extra = {"transport": transport} | ({"sleep": sleep} if sleep else {})

    reply = complete_json(settings, messages, **extra)
    result, problems = check(reply, items, resume_text)
    if problems:
        messages += [{"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)},
                     {"role": "user", "content": prompts.FIX.format(problems=" ".join(problems))}]
        reply = complete_json(settings, messages, **extra)
        result, problems = check(reply, items, resume_text)
    if problems:
        raise AIModuleError("bad_response", "Ответ ИИ не прошёл проверку критериев или цитат. Повторите анализ.")
    return result


def check(reply: dict, items: list[dict], resume: str):
    problems = []
    rows = reply.get("criteria_results")
    if not isinstance(rows, list):
        return None, ["Нет списка criteria_results."]
    by_id = {}
    for row in rows:
        if not isinstance(row, dict):
            problems.append("Элемент criteria_results не является объектом.")
            continue
        cid = row.get("criterion_id")
        if cid in by_id:
            problems.append(f"Критерий {cid} указан больше одного раза.")
        by_id[cid] = row
    expected = [item["id"] for item in items]
    missing = [cid for cid in expected if cid not in by_id]
    unknown = [str(cid) for cid in by_id if cid not in expected]
    if missing:
        problems.append(f"Нет оценки для критериев: {', '.join(missing)}.")
    if unknown:
        problems.append(f"Лишние criterion_id: {', '.join(unknown)}.")

    results = []
    for cid in expected:
        row = by_id.get(cid)
        if row is None:
            continue
        status = row.get("status")
        reason = row.get("reason")
        if status not in STATUSES:
            problems.append(f"У {cid} недопустимый статус {status!r}.")
            continue
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"У {cid} нет пояснения reason.")
            continue
        quote = None
        if status != "unconfirmed":
            quote = find_quote(row.get("quote"), resume)
            if quote is None:
                problems.append(f"У {cid} цитата не найдена в резюме дословно.")
                continue
        results.append({"criterion_id": cid, "status": status, "reason": reason.strip(), "quote": quote})
        if "match_percent" in row:
            percent = row["match_percent"]
            valid_range = {"confirmed": (100, 100), "partial": (1, 99), "unconfirmed": (0, 0)}
            low, high = valid_range[status]
            if type(percent) is not int or not low <= percent <= high:
                problems.append(f"Invalid match_percent for {cid}: expected integer from {low} to {high}.")
            else:
                results[-1]["match_percent"] = percent

    lists = {}
    for name in ("matches", "gaps", "questions"):
        value = reply.get(name, [])
        if not isinstance(value, list):
            problems.append(f"Поле {name} должно быть списком строк.")
            value = []
        lists[name] = [str(v).strip() for v in value if str(v).strip()]
    summary = reply.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("Нет summary.")
    if problems:
        return None, problems
    return {"criteria_results": results, **lists, "summary": summary.strip()}, []


def find_quote(quote, resume: str) -> str | None:
    # модель может поменять пробелы/регистр или добавить кавычки, ищем исходный кусок текста
    if not isinstance(quote, str):
        return None
    quote = quote.strip().strip(OUTER_QUOTES).strip()
    if not quote:
        return None
    if quote in resume:
        return quote
    words = quote.split()
    pattern = r"\s+".join(re.escape(word) for word in words)
    match = re.search(pattern, resume, re.IGNORECASE)
    if match is None and quote[-1] in ".…":
        return find_quote(quote.rstrip(".…"), resume)
    return match.group(0) if match else None
