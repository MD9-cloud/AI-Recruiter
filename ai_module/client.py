import json
import time

import httpx

from .config import Settings
from .errors import AIModuleError

RETRY_DELAY = 2.0
CONNECT_TIMEOUT = 10.0


def complete_json(settings: Settings, messages: list[dict], *, transport=None, sleep=time.sleep) -> dict:
    if not settings.key:
        raise AIModuleError("config", "Ключ внешнего ИИ не задан на сервере (RECRUITER_AI_KEY).")
    payload = {"model": settings.model, "messages": messages, "temperature": 0,
               "response_format": {"type": "json_object"}}
    if "deepseek.com" in settings.url:
        payload["thinking"] = {"type": "disabled"}
    headers = {"Authorization": f"Bearer {settings.key}"}
    timeout = httpx.Timeout(settings.timeout, connect=min(CONNECT_TIMEOUT, settings.timeout))
    with httpx.Client(timeout=timeout, transport=transport, follow_redirects=False) as client:
        for attempt in range(2):
            last = attempt == 1
            try:
                response = client.post(settings.url, json=payload, headers=headers)
            except httpx.TimeoutException:
                if last:
                    raise AIModuleError("timeout", "Внешний ИИ не ответил вовремя. Повторите анализ.") from None
                sleep(RETRY_DELAY)
                continue
            except httpx.RequestError:
                if last:
                    raise AIModuleError("unavailable", "Внешний ИИ недоступен. Повторите позже.") from None
                sleep(RETRY_DELAY)
                continue
            if response.status_code in (401, 403):
                raise AIModuleError("auth", "Внешний ИИ отклонил ключ. Проверьте RECRUITER_AI_KEY.")
            if response.status_code == 402:
                raise AIModuleError("auth", "На счёте внешнего ИИ закончились средства.")
            if response.status_code == 429 or response.status_code >= 500:
                if last:
                    raise AIModuleError("unavailable", "Внешний ИИ перегружен или недоступен. Повторите позже.")
                sleep(RETRY_DELAY)
                continue
            if response.status_code >= 400:
                raise AIModuleError("config", f"Внешний ИИ отклонил запрос (HTTP {response.status_code}). "
                                              "Проверьте адрес и модель.")
            return _parse(response)
    raise AIModuleError("unavailable", "Внешний ИИ недоступен. Повторите позже.")


def _parse(response: httpx.Response) -> dict:
    try:
        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        data = json.loads(content)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise AIModuleError("bad_response", "Внешний ИИ вернул ответ не в формате JSON.") from None
    if not isinstance(data, dict):
        raise AIModuleError("bad_response", "Внешний ИИ вернул ответ не в формате JSON-объекта.")
    return data
