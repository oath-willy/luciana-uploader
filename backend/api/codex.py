import logging
from functools import lru_cache
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException, Query
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


@lru_cache(maxsize=2)
def _repository(environment: CodexEnvironmentName) -> CodexRepository:
    try:
        return CodexRepository(environment)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
