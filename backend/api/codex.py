import logging
from uuid import uuid4
from functools import lru_cache
from typing import Any, Dict, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.codex_repository import (
    MAX_EXTRA_COLUMNS,
    CodexEnvironmentName,
    CodexRepository,
    environment_descriptors,
    environment_settings,
    load_mapping,
)
from services.databricks_statement import DatabricksStatementError
from services.codex_retrieval import MAX_LOOKUP_BATCH_SIZE


logger = logging.getLogger(__name__)
router = APIRouter()

CodexView = Literal["light", "full"]
PAGE_SIZE_OPTIONS = {25, 50, 100, 250, 500}


class CodexColumn(BaseModel):
    field: str
    header_name: str
    value_type: Literal["string", "number", "boolean", "date"] = "string"


class CodexCompany(BaseModel):
    value: str
    label: str
    full_view_available: bool
    full_view_message: str | None = None


class CodexSearchRequest(BaseModel):
    environment: CodexEnvironmentName = "dev"
    company: str = Field(min_length=1, max_length=255)
    view: CodexView = "light"
    page: int = 0
    page_size: int = 100
    search: str = ""
    filters: Dict[str, Any] = Field(default_factory=dict)


class CodexDetailRequest(BaseModel):
    environment: CodexEnvironmentName = "dev"
    company: str = Field(min_length=1, max_length=255)
    item_code: str = Field(min_length=1, max_length=255)


class CodexBs25LookupRequest(BaseModel):
    environment: CodexEnvironmentName = "dev"
    company: str = Field(min_length=1, max_length=255)
    item_codes: list[str] = Field(min_length=1, max_length=MAX_LOOKUP_BATCH_SIZE)


class CodexBs25SelectionRequest(BaseModel):
    environment: CodexEnvironmentName = "dev"
    company: str = Field(min_length=1, max_length=255)
    item_code: str = Field(min_length=1, max_length=255)
    proposal_rank: int = Field(ge=1, le=3)
    selection_request_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=64,
    )


class CodexSearchResponse(BaseModel):
    rows: list[Dict[str, Any]]
    total: int
    extra_columns: list[CodexColumn] = Field(
        default_factory=list,
        max_length=MAX_EXTRA_COLUMNS,
    )


class CodexDetailResponse(BaseModel):
    record: Dict[str, Any]
    extra_columns: list[CodexColumn] = Field(
        default_factory=list,
        max_length=MAX_EXTRA_COLUMNS,
    )


@router.get("/codex/config")
def get_codex_config():
    dev_settings = environment_settings("dev")
    mapping_source, _ = load_mapping("dev")
    return {
        "default_environment": "dev",
        "environments": environment_descriptors(),
        "dataset_name": dev_settings.dataset_name,
        "max_extra_columns": MAX_EXTRA_COLUMNS,
        "fuzzy_lookup_actions_available": False,
        "ai_lookup_actions_available": False,
        "bs25_actions_available": True,
        "lookup_actions_available": False,
        "mapping_source": mapping_source,
    }


@router.get("/codex/companies", response_model=list[CodexCompany])
def get_codex_companies(
    environment: CodexEnvironmentName = Query(default="dev"),
):
    return _repository(environment).companies()


@router.post("/codex/search", response_model=CodexSearchResponse)
def search_codex_rows(request: CodexSearchRequest):
    if request.page < 0:
        raise HTTPException(status_code=400, detail="La pagina non puo essere negativa")
    if request.page_size not in PAGE_SIZE_OPTIONS:
        raise HTTPException(status_code=400, detail="Rows per page non valido")

    try:
        return _repository(request.environment).search(
            company=request.company,
            view=request.view,
            page=request.page,
            page_size=request.page_size,
            search=request.search,
            filters=request.filters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatabricksStatementError as exc:
        logger.exception("Errore query CODEX su Databricks")
        raise HTTPException(
            status_code=502,
            detail="Databricks non ha completato la richiesta CODEX",
        ) from exc


@router.post("/codex/detail", response_model=CodexDetailResponse)
def get_codex_detail(request: CodexDetailRequest):
    try:
        detail = _repository(request.environment).detail(
            company=request.company,
            item_code=request.item_code,
        )
    except DatabricksStatementError as exc:
        logger.exception("Errore dettaglio CODEX su Databricks")
        raise HTTPException(
            status_code=502,
            detail="Databricks non ha completato la richiesta di dettaglio",
        ) from exc

    if detail is None:
        raise HTTPException(status_code=404, detail="Record CODEX non trovato")
    return detail


@router.post("/codex/bs25", status_code=202)
def submit_codex_bs25_lookup(
    payload: CodexBs25LookupRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    item_codes = list(dict.fromkeys(item_code.strip() for item_code in payload.item_codes))
    if any(not item_code for item_code in item_codes):
        raise HTTPException(status_code=400, detail="Item code vuoto non consentito")

    repository = _repository(payload.environment)
    try:
        result = repository.submit_bs25_lookup(
            company=payload.company,
            item_codes=item_codes,
            requested_by=_request_actor(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatabricksStatementError as exc:
        logger.exception("Errore creazione lookup BS25 su Databricks")
        raise HTTPException(
            status_code=502,
            detail="Databricks non ha accettato la richiesta BS25",
        ) from exc

    accepted = result["accepted_item_codes"]
    if accepted:
        background_tasks.add_task(
            _run_bs25_background,
            payload.environment,
            payload.company,
            accepted,
        )
    return result


@router.post("/codex/bs25/select", status_code=202)
def select_codex_bs25_proposal(
    payload: CodexBs25SelectionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    selection_request_id = payload.selection_request_id or uuid4().hex
    try:
        _repository(payload.environment).queue_bs25_selection(
            company=payload.company,
            item_code=payload.item_code,
            proposal_rank=payload.proposal_rank,
            selection_request_id=selection_request_id,
        )
    except DatabricksStatementError as exc:
        logger.exception("Errore accodamento proposta BS25")
        raise HTTPException(
            status_code=502,
            detail="Databricks non ha accettato la scelta BS25",
        ) from exc
    background_tasks.add_task(
        _run_bs25_selection_background,
        payload.environment,
        payload.company,
        payload.item_code,
        payload.proposal_rank,
        _request_actor(request),
        selection_request_id,
    )
    return {
        "selection_request_id": selection_request_id,
        "selection_status": "saving",
        "proposal_rank": payload.proposal_rank,
    }


def _run_bs25_background(
    environment: CodexEnvironmentName,
    company: str,
    item_codes: list[str],
) -> None:
    try:
        _repository(environment).run_bs25_lookup(company, item_codes)
    except Exception:
        logger.exception("Lookup BS25 CODEX terminato con errore")


def _run_bs25_selection_background(
    environment: CodexEnvironmentName,
    company: str,
    item_code: str,
    proposal_rank: int,
    selected_by: str,
    selection_request_id: str,
) -> None:
    try:
        _repository(environment).complete_bs25_selection(
            company=company,
            item_code=item_code,
            proposal_rank=proposal_rank,
            selected_by=selected_by,
            selection_request_id=selection_request_id,
        )
    except Exception:
        logger.exception("Salvataggio asincrono proposta BS25 terminato con errore")


def _request_actor(request: Request) -> str:
    return (
        request.headers.get("x-ms-client-principal-name")
        or request.headers.get("x-ms-client-principal-id")
        or "webapp-user"
    )


@lru_cache(maxsize=2)
def _repository(environment: CodexEnvironmentName) -> CodexRepository:
    try:
        return CodexRepository(environment)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
