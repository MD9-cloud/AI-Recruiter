from .errors import AIModuleError


def normalize(criteria) -> list[dict]:
    items = []
    for raw in criteria or []:
        get = raw.get if isinstance(raw, dict) else (lambda name, default=None, obj=raw: getattr(obj, name, default))
        cid, text = get("id"), get("text")
        if not isinstance(cid, str) or not cid.strip() or not isinstance(text, str) or not text.strip():
            raise AIModuleError("bad_input", "У каждого критерия должны быть id и формулировка.")
        required = bool(get("required", True))
        items.append({"id": cid.strip(), "text": text.strip(), "required": required,
                      "weight": get("weight") or (2 if required else 1)})
    if not items:
        raise AIModuleError("bad_input", "Добавьте хотя бы один подтверждённый HR критерий.")
    if len({item["id"] for item in items}) != len(items):
        raise AIModuleError("bad_input", "Идентификаторы критериев должны быть уникальными.")
    return items
