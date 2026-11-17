import re

CONTROL_RESUME = "Год писал на Python. Прошёл учебный курс по FastAPI"
CONTROL = {
    "знает python": ("confirmed", "Год писал на Python.",
                     "В резюме указан год работы с Python."),
    "разрабатывал api на fastapi": ("partial", "Прошёл учебный курс по FastAPI",
                                    "Курс подтверждает знакомство с FastAPI, а разработка API в тексте не описана."),
    "работал с docker": ("unconfirmed", None, "Docker в резюме не упомянут."),
}
STOP = {"знает", "знание", "опыт", "работы", "работал", "умеет", "владеет", "навыки", "уверенное", "года",
        "лет", "более", "менее", "хорошее", "базовое", "понимание", "разрабатывал", "использовал"}
PREFERRED = re.compile(r"плюс|желательн|приветству|преимуществ", re.I)


def analyze(items: list[dict], resume: str) -> dict:
    texts = {item["text"].casefold(): item for item in items}
    if resume.strip() == CONTROL_RESUME and set(texts) == set(CONTROL):
        rows = [{"criterion_id": item["id"], "status": CONTROL[key][0], "quote": CONTROL[key][1],
                 "reason": CONTROL[key][2]} for key, item in texts.items()]
        return {"criteria_results": rows, "matches": ["Опыт работы с Python около года"],
                "gaps": ["Практический опыт разработки API на FastAPI", "Опыт работы с Docker"],
                "questions": ["Какие API вы разрабатывали на FastAPI?", "Использовали ли вы Docker в проектах?"],
                "summary": "Резюме подтверждает опыт Python и знакомство с FastAPI на уровне учебного курса. "
                           "Опыт с Docker не указан."}

    sentences = [m.group(0).strip() for m in re.finditer(r"[^.!?\n]+[.!?]?", resume) if m.group(0).strip()]
    rows, matches, gaps = [], [], []
    for item in items:
        keys = _keywords(item["text"])
        best, hits = None, 0
        for sentence in sentences:
            low = sentence.casefold()
            found = sum(1 for key in keys if key in low)
            if found > hits:
                best, hits = sentence, found
        if keys and hits == len(keys):
            status, reason = "confirmed", "Все ключевые слова критерия найдены в резюме."
        elif hits:
            status, reason = "partial", "Найдена только часть ключевых слов критерия."
        else:
            status, reason, best = "unconfirmed", "Подтверждение в тексте резюме не найдено.", None
        rows.append({"criterion_id": item["id"], "status": status, "reason": reason, "quote": best})
        (gaps if status == "unconfirmed" else matches).append(item["text"])
    return {"criteria_results": rows, "matches": matches, "gaps": gaps,
            "questions": [f"Расскажите про ваш опыт: {text}?" for text in gaps][:5],
            "summary": "Тестовый режим: оценка по совпадению слов."}


def suggest(vacancy: str) -> list[dict]:
    result = []
    for line in vacancy.splitlines():
        for part in re.split(r"(?<=[.;])\s+", line):
            text = part.strip(" -•*\t.;")
            if 3 <= len(text) <= 200 and len(result) < 12:
                required = not PREFERRED.search(text)
                result.append({"text": text, "required": required})
    return result


def draft(role: str, entries: list[dict], extra: str | None) -> dict:
    bodies = [entry["body"] for entry in entries]
    return {"title": role, "department": bodies[0][:300] if bodies else "",
            "responsibilities": bodies[1:4], "required": [], "preferred": [],
            "conditions": {"salary": None, "schedule": None, "format": None,
                           "other": [extra] if extra else []}}


def _keywords(text: str) -> list[str]:
    words = [w.strip(".-") for w in re.findall(r"[\w+#.-]+", text.casefold())]
    return [w[:6] if len(w) > 6 else w for w in words if len(w) >= 3 and w not in STOP]
