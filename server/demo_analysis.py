from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

import ai_module

from .ai import weighted_percentage
from .files import MAX_BYTES, MAX_TEXT, extract
from .storage import connect

router = APIRouter(prefix="/api/demo/analyses", tags=["Контрольный анализ"])

CONTROL_RESUME = "Год писал на Python. Прошёл учебный курс по FastAPI"
CONTROL_CRITERIA = {
    "c1": "знает Python",
    "c2": "разрабатывал API на FastAPI",
    "c3": "работал с Docker",
}
FACTORS = {"confirmed": 1, "partial": 0.5, "unconfirmed": 0}


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=500)
    required: bool = Field(strict=True)
    weight: int = Field(default_factory=lambda data: 2 if data["required"] else 1, ge=1, le=5, strict=True)


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_name: str = Field(default="", max_length=120)
    vacancy_text: str = Field(min_length=1, max_length=MAX_TEXT)
    criteria: list[Criterion] = Field(max_length=50)
    resume_text: str = Field(min_length=1, max_length=MAX_TEXT)

    @model_validator(mode="after")
    def check_texts(self):
        if not self.vacancy_text.strip() or not self.resume_text.strip():
            raise ValueError("Введите текст вакансии и резюме.")
        return self


class CriterionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    status: Literal["confirmed", "partial", "unconfirmed"]
    reason: str = Field(min_length=1)
    quote: str | None
    match_percent: int | None = Field(default=None, ge=0, le=100, strict=True)


class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria_results: list[CriterionResult]
    matches: list[str]
    gaps: list[str]
    questions: list[str]
    summary: str = Field(min_length=1)


class SavedAnalysis(ProviderResult):
    candidate_name: str = Field(default="", max_length=120)
    analysis_id: UUID
    score_percent: float
    criteria: list[Criterion]
    unconfirmed_required: list[Criterion]


def fixed_provider(criteria: list[Criterion], resume_text: str) -> dict:
    if {item.id: item.text for item in criteria} != CONTROL_CRITERIA or resume_text.strip() != CONTROL_RESUME:
        raise HTTPException(422, "Учебный адаптер принимает контрольное резюме и критерии c1, c2, c3 из README.")
    return {
        "criteria_results": [
            {"criterion_id": "c1", "status": "confirmed", "reason": "Указан год работы с Python.",
             "quote": "Год писал на Python."},
            {"criterion_id": "c2", "status": "partial", "reason": "Есть учебный курс, опыт разработки API не указан.",
             "quote": "Прошёл учебный курс по FastAPI"},
            {"criterion_id": "c3", "status": "unconfirmed", "reason": "Docker в резюме не упомянут.",
             "quote": None},
        ],
        "matches": ["Python"],
        "gaps": ["Практический опыт разработки API на FastAPI", "Опыт работы с Docker"],
        "questions": ["Какие API вы разрабатывали на FastAPI?", "Использовали ли вы Docker в проектах?"],
        "summary": "Резюме подтверждает опыт Python и показывает знакомство с FastAPI на уровне курса.",
    }


def analysis_provider(criteria: list[Criterion], resume_text: str, vacancy_text: str) -> dict:
    if ai_module.load_settings().mode == "stub":
        return fixed_provider(criteria, resume_text)
    try:
        return ai_module.analyze_resume(criteria, resume_text, vacancy_text)
    except ai_module.AIModuleError as exc:
        raise HTTPException(exc.http_status, exc.message) from None


def validate_provider_result(reply: dict, criteria: dict[str, Criterion], resume_text: str) -> ProviderResult:
    try:
        result = ProviderResult.model_validate(reply)
    except ValidationError:
        raise HTTPException(502, "Ответ модуля ИИ не соответствует формату критериев, статусов или цитат.") from None
    returned_ids = [row.criterion_id for row in result.criteria_results]
    if len(returned_ids) != len(criteria) or set(returned_ids) != criteria.keys():
        raise HTTPException(502, "Модуль ИИ должен вернуть каждый критерий ровно один раз.")
    for row in result.criteria_results:
        if row.status == "unconfirmed":
            valid = row.quote is None
        else:
            valid = bool(row.quote and row.quote.strip() and row.quote in resume_text)
        if not valid:
            raise HTTPException(502, f"Некорректная цитата в ответе модуля ИИ для критерия {row.criterion_id}.")
    return result


@router.post("", response_model=SavedAnalysis, status_code=201)
def create_analysis(payload: AnalysisInput):
    return create_saved_analysis(payload, None)


def create_saved_analysis(payload: AnalysisInput, owner_id: int | None):
    criteria = {item.id: item for item in payload.criteria}
    if not criteria:
        raise HTTPException(422, "Добавьте хотя бы один подтверждённый HR критерий.")
    if len(criteria) != len(payload.criteria):
        raise HTTPException(422, "Идентификаторы критериев должны быть уникальными.")

    reply = analysis_provider(payload.criteria, payload.resume_text, payload.vacancy_text)
    result = validate_provider_result(reply, criteria, payload.resume_text)
    results_by_id = {row.criterion_id: row for row in result.criteria_results}
    result.criteria_results = [results_by_id[item_id] for item_id in criteria]

    saved = SavedAnalysis(
        **result.model_dump(),
        analysis_id=uuid4(),
        candidate_name=payload.candidate_name.strip(),
        criteria=payload.criteria,
        score_percent=weighted_percentage(
            (criteria[row.criterion_id].weight, row.match_percent / 100 if row.match_percent is not None else FACTORS[row.status])
            for row in result.criteria_results
        ),
        unconfirmed_required=[
            criteria[row.criterion_id] for row in result.criteria_results
            if row.status == "unconfirmed" and criteria[row.criterion_id].required
        ],
    )
    with connect() as db:
        db.execute("INSERT INTO demo_analyses(id,result,owner_id) VALUES(?,?,?)", (str(saved.analysis_id), saved.model_dump_json(), owner_id))
    return saved


class AnalysisHistoryItem(BaseModel):
    candidate_name: str = Field(default="", max_length=120)
    analysis_id: UUID
    score_percent: float


@router.get("", response_model=list[AnalysisHistoryItem])
def analysis_history():
    return analysis_history_for(None)


def analysis_history_for(owner_id: int | None):
    with connect() as db:
        rows = db.execute(
            "SELECT id, json_extract(result, '$.score_percent') AS score_percent "
            " , COALESCE(json_extract(result, '$.candidate_name'), '') AS candidate_name "
            "FROM demo_analyses WHERE owner_id IS ? ORDER BY rowid DESC LIMIT 20", (owner_id,)
        ).fetchall()
    return [AnalysisHistoryItem(analysis_id=row["id"], score_percent=row["score_percent"], candidate_name=row["candidate_name"]) for row in rows]


@router.delete("", status_code=204)
def clear_analysis_history():
    return clear_analysis_history_for(None)


def clear_analysis_history_for(owner_id: int | None):
    with connect() as db:
        db.execute("DELETE FROM demo_analyses WHERE owner_id IS ?", (owner_id,))


@router.post("/resume-text")
def extract_resume_text(file: UploadFile = File(...)):
    try:
        return {"text": extract(file.filename or "", file.file.read(MAX_BYTES + 1))}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/{analysis_id}", response_model=SavedAnalysis)
def get_analysis(analysis_id: UUID):
    return get_analysis_for(analysis_id, None)


def get_analysis_for(analysis_id: UUID, owner_id: int | None):
    with connect() as db:
        row = db.execute("SELECT result FROM demo_analyses WHERE id=? AND owner_id IS ?", (str(analysis_id), owner_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Анализ с таким ID не найден.")
    return SavedAnalysis.model_validate_json(row["result"])
