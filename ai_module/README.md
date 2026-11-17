# ai_module

ИИ-часть проекта. Модуль вызывается сервером, своего API у него нет.

Функции:
- `analyze_resume(criteria, resume_text, vacancy_text=None)` — оценка резюме по критериям, возвращает
  `criteria_results` (criterion_id, status, reason, quote), `matches`, `gaps`, `questions`, `summary`.
  Процент считает сервер.
- `suggest_criteria(vacancy_text)` — критерии из текста вакансии.
- `draft_vacancy(role, knowledge, extra=None, level=None)` — черновик вакансии по базе знаний.
  Если зарплата, график или формат не указаны, остаются поля `[Укажите ...]`.

Статусы: `confirmed`, `partial`, `unconfirmed`. Для `unconfirmed` quote = null.

Ошибки приходят как `AIModuleError` (поля `kind`, `message`, `http_status`).

## Настройка

Без ключа модуль работает в тестовом режиме. Для DeepSeek создать `.env` в корне репозитория
(он в .gitignore):

```
RECRUITER_AI_KEY=sk-...
RECRUITER_AI_MODEL=deepseek-flash
```

Можно поменять `RECRUITER_AI_URL` на любой OpenAI-совместимый API. `RECRUITER_AI_TIMEOUT` — тайм-аут в секундах (по умолчанию 60).

## Запуск

```
python -m ai_module analyze
python -m ai_module suggest
python -m ai_module draft
python -m unittest tests.test_ai_module
python -m uvicorn server.main:app --port 8000
```

`POST /api/demo/analyses` без ключа работает на заглушке, с ключом — через ai_module.
Тесты всегда запускаются без внешнего ИИ.
