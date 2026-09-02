import os
import secrets
import tempfile
from pathlib import Path
from typing import Any, Dict, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.codex_bs25ai import (
    bs25ai_mock_mode,
    complete_human_review_goal,
    run_bs25ai_job,
    run_bs25ai_xhigh,
)
from services.codex_local_bs25 import run_local_bs25_batch
from services.codex_local_retrieval import (
    LocalPdbBm25Retriever,
    pdb_environment_status,
    validate_and_publish_pdb_file,
)
from services.codex_local_store import (
    MAX_EXTRA_COLUMNS,
    CodexEnvironmentName,
    CodexSnapshotStore,
    RuntimeStore,
    SnapshotUnavailable,
    SnapshotValidationError,
    codex_data_dir,
    environment_descriptors,
    publish_snapshot,
)
from services.codex_selection import resolve_codex_selection


router = APIRouter()

CodexView = Literal["light", "full"]
PAGE_SIZE_OPTIONS = {25, 50, 100, 250, 500}
MAX_BS25AI_BATCH_SIZE = 5000
MAX_BS25_BATCH_SIZE = 20


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


class CodexItemsRequest(BaseModel):
    environment: CodexEnvironmentName = "dev"
    company: str = Field(min_length=1, max_length=255)
    item_codes: list[str] = Field(min_length=1, max_length=MAX_BS25AI_BATCH_SIZE)


class CodexEligibleRequest(BaseModel):
    environment: CodexEnvironmentName = "dev"
    company: str = Field(min_length=1, max_length=255)
    view: CodexView = "light"
    search: str = ""
    filters: Dict[str, Any] = Field(default_factory=dict)


class CodexItemActionRequest(BaseModel):
    environment: CodexEnvironmentName = "dev"
    company: str = Field(min_length=1, max_length=255)
    item_code: str = Field(min_length=1, max_length=255)


class CodexBs25SelectionRequest(CodexItemActionRequest):
    proposal_rank: int | None = Field(default=None, ge=1, le=3)
    clear: bool = False
    selection_request_id: str | None = Field(default=None, min_length=16, max_length=64)


class CodexSearchResponse(BaseModel):
    rows: list[Dict[str, Any]]
    total: int
    extra_columns: list[CodexColumn] = Field(default_factory=list, max_length=MAX_EXTRA_COLUMNS)


class CodexDetailResponse(BaseModel):
    record: Dict[str, Any]
    extra_columns: list[CodexColumn] = Field(default_factory=list, max_length=MAX_EXTRA_COLUMNS)


class SnapshotCompany(BaseModel):
    company: str
    full_view_available: bool = False
    full_view_message: str | None = None
    extra_columns: list[CodexColumn] = Field(default_factory=list, max_length=MAX_EXTRA_COLUMNS)


class SnapshotMasterCode(BaseModel):
    master_code: str
    components: Dict[str, Any] = Field(default_factory=dict)


class SnapshotPayload(BaseModel):
    environment: CodexEnvironmentName
    snapshot_id: str = Field(min_length=1, max_length=255)
    created_at: str
    companies: list[SnapshotCompany]
    rows: list[Dict[str, Any]] = Field(min_length=1)
    master_codes: list[SnapshotMasterCode] = Field(min_length=1)


@router.get("/codex/config")
def get_codex_config():
    descriptors = environment_descriptors()
    available = next((item["value"] for item in descriptors if item["available"]), "dev")
    pdb_available = pdb_environment_status()
    return {
        "default_environment": available,
        "environments": descriptors,
        "dataset_name": "local CODEX snapshot",
        "max_extra_columns": MAX_EXTRA_COLUMNS,
        "fuzzy_lookup_actions_available": False,
        "ai_lookup_actions_available": False,
        "bs25_actions_available": any(pdb_available.values()),
        "bs25ai_actions_available": True,
        "lookup_actions_available": False,
        "data_source": "local_snapshot",
        "pdb_available": pdb_available,
        "bs25ai_mock_mode": bs25ai_mock_mode(),
    }


@router.get("/codex/companies", response_model=list[CodexCompany])
def get_codex_companies(environment: CodexEnvironmentName = Query(default="dev")):
    return _snapshot(environment).companies()


@router.post("/codex/search", response_model=CodexSearchResponse)
def search_codex_rows(payload: CodexSearchRequest):
    if payload.page < 0:
        raise HTTPException(status_code=400, detail="La pagina non puo essere negativa")
    if payload.page_size not in PAGE_SIZE_OPTIONS:
        raise HTTPException(status_code=400, detail="Rows per page non valido")
    try:
        return _snapshot(payload.environment).search(
            payload.company,
            payload.view,
            payload.page,
            payload.page_size,
            payload.search,
            payload.filters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/codex/detail", response_model=CodexDetailResponse)
def get_codex_detail(payload: CodexDetailRequest):
    detail = _snapshot(payload.environment).detail(payload.company, payload.item_code)
    if detail is None:
        raise HTTPException(status_code=404, detail="Record CODEX non trovato")
    return detail


@router.post("/codex/bs25ai/eligible")
def eligible_bs25ai_rows(payload: CodexEligibleRequest):
    rows = _snapshot(payload.environment).eligible(
        payload.company, payload.view, payload.search, payload.filters
    )
    return {"rows": rows, "total": len(rows)}


@router.post("/codex/bs25", status_code=202)
def submit_local_bs25(
    payload: CodexItemsRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    item_codes = _normalized_item_codes(payload.item_codes)
    if len(item_codes) > MAX_BS25_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Seleziona al massimo {MAX_BS25_BATCH_SIZE} record per analisi BS25",
        )
    try:
        LocalPdbBm25Retriever(payload.environment).metadata()
    except SnapshotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    snapshot = _snapshot(payload.environment)
    items = snapshot.get_items(payload.company, item_codes)
    items_by_code = {item["item_code"]: item for item in items}
    missing = [code for code in item_codes if code not in items_by_code]
    if missing:
        raise HTTPException(status_code=404, detail=f"Item CODEX non trovato: {missing[0]}")

    runtime = RuntimeStore()
    accepted: list[str] = []
    locked: list[str] = []
    for item_code in item_codes:
        item = items_by_code[item_code]
        if item.get("bs25_status") == "completed" and all(
            isinstance(item.get(f"bs25_proposal_{rank}"), dict) for rank in (1, 2, 3)
        ):
            locked.append(item_code)
            continue
        if runtime.create_bs25_job(
            payload.environment,
            payload.company,
            item_code,
            uuid4().hex,
            _request_actor(request),
        ):
            accepted.append(item_code)
        else:
            locked.append(item_code)
    if accepted:
        background_tasks.add_task(
            run_local_bs25_batch,
            payload.environment,
            payload.company,
            accepted,
        )
    return {"accepted_item_codes": accepted, "locked_item_codes": locked}


@router.post("/codex/bs25ai", status_code=202)
def submit_bs25ai(
    payload: CodexItemsRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    item_codes = _normalized_item_codes(payload.item_codes)
    snapshot = _snapshot(payload.environment)
    items = snapshot.get_items(payload.company, item_codes)
    items_by_code = {item["item_code"]: item for item in items}
    missing = [code for code in item_codes if code not in items_by_code]
    if missing:
        raise HTTPException(status_code=404, detail=f"Item CODEX non trovato: {missing[0]}")

    runtime = RuntimeStore()
    accepted: list[str] = []
    locked: list[str] = []
    invalid: list[str] = []
    for item_code in item_codes:
        item = items_by_code[item_code]
        if item.get("bs25_status") != "completed" or not all(
            isinstance(item.get(f"bs25_proposal_{rank}"), dict) for rank in (1, 2, 3)
        ):
            invalid.append(item_code)
            continue
        if item.get("bs25_selection_status") or item.get("bs25_selected_source"):
            invalid.append(item_code)
            continue
        if runtime.create_job(
            payload.environment,
            payload.company,
            item_code,
            uuid4().hex,
            _request_actor(request),
        ):
            accepted.append(item_code)
            background_tasks.add_task(
                run_bs25ai_job, payload.environment, payload.company, item_code
            )
        else:
            locked.append(item_code)
    return {
        "accepted_item_codes": accepted,
        "locked_item_codes": locked,
        "invalid_item_codes": invalid,
    }


@router.post("/codex/bs25ai/escalate", status_code=202)
def escalate_bs25ai(payload: CodexItemActionRequest, background_tasks: BackgroundTasks):
    runtime = RuntimeStore()
    job = runtime.get_job(payload.environment, payload.company, payload.item_code)
    if not job or job.get("status") not in {"completed", "failed", "needs_human_review"}:
        raise HTTPException(status_code=409, detail="Analisi Sol low non pronta per xhigh")
    if not job.get("thread_id"):
        raise HTTPException(status_code=409, detail="Thread Sol low non disponibile")
    runtime.update_job(
        payload.environment,
        payload.company,
        payload.item_code,
        status="queued",
        stage="sol_xhigh_web",
        goal_status="active",
        error_message=None,
    )
    background_tasks.add_task(
        run_bs25ai_xhigh, payload.environment, payload.company, payload.item_code
    )
    return {"status": "accepted", "stage": "sol_xhigh_web"}


@router.post("/codex/bs25ai/decline")
def decline_bs25ai(payload: CodexItemActionRequest, background_tasks: BackgroundTasks):
    runtime = RuntimeStore()
    job = runtime.get_job(payload.environment, payload.company, payload.item_code)
    if not job:
        raise HTTPException(status_code=404, detail="Analisi BS25AI non trovata")
    if job.get("stage") != "sol_low" or job.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Sol low non pronto per la decisione")
    runtime.update_job(
        payload.environment,
        payload.company,
        payload.item_code,
        status="needs_human_review",
        goal_status="complete",
        flag="Escalation Sol xhigh non richiesta: revisione umana necessaria.",
    )
    if job.get("thread_id"):
        background_tasks.add_task(complete_human_review_goal, job["thread_id"])
    return {"status": "needs_human_review"}


@router.post("/codex/bs25ai/retry", status_code=202)
def retry_bs25ai(payload: CodexItemActionRequest, background_tasks: BackgroundTasks):
    runtime = RuntimeStore()
    job = runtime.get_job(payload.environment, payload.company, payload.item_code)
    if not job or job.get("status") != "failed":
        raise HTTPException(status_code=409, detail="Nessun errore BS25AI da ritentare")
    runtime.update_job(
        payload.environment,
        payload.company,
        payload.item_code,
        status="queued",
        error_message=None,
    )
    runner = run_bs25ai_xhigh if job.get("stage") == "sol_xhigh_web" else run_bs25ai_job
    background_tasks.add_task(runner, payload.environment, payload.company, payload.item_code)
    return {"status": "accepted", "stage": job.get("stage")}


@router.post("/codex/bs25/select")
def save_codex_selection(payload: CodexBs25SelectionRequest, request: Request):
    try:
        selection = resolve_codex_selection(payload.proposal_rank, payload.clear)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    item = _snapshot(payload.environment).get_items(payload.company, [payload.item_code])
    if not item:
        raise HTTPException(status_code=404, detail="Item CODEX non trovato")
    master_code = None
    if selection.kind == "proposal":
        proposal = item[0].get(f"bs25_proposal_{selection.proposal_rank}") or {}
        master_code = str(proposal.get("master_code") or "").strip().upper() or None
        if not master_code:
            raise HTTPException(status_code=400, detail="Proposta BS25 priva di Master Code")
    if selection.kind == "proposal" and master_code and not _snapshot(
        payload.environment
    ).has_master_code(master_code):
        raise HTTPException(status_code=400, detail="Master Code non presente nello snapshot canonico")

    return RuntimeStore().save_selection(
        payload.environment,
        payload.company,
        payload.item_code,
        selection.kind,
        selection.proposal_rank,
        master_code,
        payload.selection_request_id or uuid4().hex,
        _request_actor(request),
    )


@router.put("/codex/snapshot")
def ingest_codex_snapshot(
    payload: SnapshotPayload,
    x_codex_snapshot_token: str | None = Header(default=None),
):
    expected = os.getenv("CODEX_SNAPSHOT_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Ingest snapshot CODEX non configurato")
    if not x_codex_snapshot_token or not secrets.compare_digest(
        x_codex_snapshot_token, expected
    ):
        raise HTTPException(status_code=401, detail="Token snapshot CODEX non valido")
    try:
        return publish_snapshot(
            payload.environment,
            payload.snapshot_id,
            payload.created_at,
            [item.model_dump() for item in payload.companies],
            payload.rows,
            [item.model_dump() for item in payload.master_codes],
        )
    except SnapshotValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/codex/pdb-snapshot")
async def ingest_pdb_snapshot(
    request: Request,
    environment: CodexEnvironmentName = Query(default="dev"),
    x_codex_snapshot_token: str | None = Header(default=None),
):
    """Accept a prebuilt SQLite index without loading the PDB into app memory."""
    expected = os.getenv("CODEX_SNAPSHOT_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Ingest snapshot CODEX non configurato")
    if not x_codex_snapshot_token or not secrets.compare_digest(
        x_codex_snapshot_token, expected
    ):
        raise HTTPException(status_code=401, detail="Token snapshot CODEX non valido")

    data_dir = codex_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".pdb-{environment}-upload-", suffix=".sqlite3", dir=data_dir
    )
    os.close(descriptor)
    staged = Path(temporary_name)
    try:
        with staged.open("wb") as handle:
            async for chunk in request.stream():
                handle.write(chunk)
        return validate_and_publish_pdb_file(environment, staged)
    except SnapshotValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        staged.unlink(missing_ok=True)


@router.get("/codex/snapshot/status")
def codex_snapshot_status(environment: CodexEnvironmentName = Query(default="dev")):
    store = _snapshot(environment)
    return {"environment": environment, **store.metadata()}


@router.get("/codex/pdb-snapshot/status")
def codex_pdb_snapshot_status(environment: CodexEnvironmentName = Query(default="dev")):
    try:
        return {"environment": environment, **LocalPdbBm25Retriever(environment).metadata()}
    except SnapshotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _snapshot(environment: CodexEnvironmentName) -> CodexSnapshotStore:
    store = CodexSnapshotStore(environment)
    if not store.path.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"Snapshot locale CODEX non disponibile: {store.path.name}",
        )
    try:
        return store
    except SnapshotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _normalized_item_codes(item_codes: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(item_code.strip() for item_code in item_codes))
    if any(not item_code for item_code in normalized):
        raise HTTPException(status_code=400, detail="Item code vuoto non consentito")
    return normalized


def _request_actor(request: Request) -> str:
    return (
        request.headers.get("x-ms-client-principal-name")
        or request.headers.get("x-ms-client-principal-id")
        or "webapp-user"
    )
