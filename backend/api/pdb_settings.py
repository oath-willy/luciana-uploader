from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from services.pdb_ref_sync import (
    PdbRefSyncStore,
    pdb_ref_status,
    pdb_ref_sync_configured,
    run_pdb_ref_sync,
)
from services.pdb_new_items_sync import new_items_job_store, new_items_status, run_new_items_sync


router = APIRouter(prefix="/pdb/settings", tags=["PDB Settings"])


@router.get("/new-items")
def get_new_items_status():
    return new_items_status()


@router.post("/new-items/refresh", status_code=202)
def refresh_new_items(background_tasks: BackgroundTasks, request: Request):
    request_id = uuid4().hex
    requested_by = request.headers.get("x-ms-client-principal-name") or "webapp-user"
    if not new_items_job_store().claim(request_id, requested_by):
        raise HTTPException(status_code=409, detail="Un aggiornamento New Items e gia in corso")
    background_tasks.add_task(run_new_items_sync, request_id)
    return new_items_status()


@router.get("/ref-dump")
def get_ref_pdb_dump_status():
    return pdb_ref_status()


@router.post("/ref-dump/refresh", status_code=202)
def refresh_ref_pdb_dump(background_tasks: BackgroundTasks, request: Request):
    if not pdb_ref_sync_configured():
        raise HTTPException(
            status_code=503,
            detail="Connessione SSH a lucianavm04 non configurata",
        )
    request_id = uuid4().hex
    requested_by = (
        request.headers.get("x-ms-client-principal-name")
        or request.headers.get("x-ms-client-principal-id")
        or "webapp-user"
    )
    if not PdbRefSyncStore().claim(request_id, requested_by):
        raise HTTPException(
            status_code=409,
            detail="Un aggiornamento del Reference PDB e gia in corso",
        )
    background_tasks.add_task(run_pdb_ref_sync, request_id)
    return pdb_ref_status()
