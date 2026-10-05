from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, StreamingResponse

from services import fast_track


def require_fast_track_user(request: Request) -> str:
    if not fast_track.enabled():
        raise HTTPException(404, "Fast Track disabilitato")
    cloud = bool(os.getenv("WEBSITE_SITE_NAME") or os.getenv("WEBSITE_INSTANCE_ID"))
    mode = os.getenv("FAST_TRACK_AUTH_MODE", "disabled" if cloud else "local")
    if mode == "local" and not cloud:
        if request.url.hostname in {"localhost", "127.0.0.1", "::1"} and request.client and request.client.host in {"127.0.0.1", "::1"}:
            return "local@dev"
        raise HTTPException(403, "Accesso locale consentito solo da localhost")
    # Trust the platform header only after Easy Auth + the SWA linked gateway are enabled.
    # The production default fails closed until this explicit infrastructure configuration.
    if mode != "linked" or os.getenv("APP_AUTH_GATEWAY_ENABLED", os.getenv("WEBSITE_AUTH_ENABLED", "")).lower() != "true":
        raise HTTPException(503, "Accesso Fast Track non configurato: collegare il backend autenticato alla webapp")
    try:
        principal = json.loads(base64.b64decode(request.headers.get("x-ms-client-principal", ""), validate=True))
        email = str(principal["userDetails"]).lower()
        if "authenticated" not in principal["userRoles"] or principal["identityProvider"] != "aad":
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, "Accesso autenticato richiesto")
    if not (email.endswith("@key-stone.it") or email == "matteo@finstat.it"):
        raise HTTPException(403, "Utente non autorizzato")
    origin = request.headers.get("origin")
    allowed = {os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
               "https://yellow-forest-0ad79d503.6.azurestaticapps.net"}
    if request.method == "POST" and origin and origin not in allowed:
        raise HTTPException(403, "Origine della richiesta non autorizzata")
    return email


router = APIRouter(prefix="/fast-track", tags=["Fast Track"], dependencies=[Depends(require_fast_track_user)])
_file_slots = asyncio.Semaphore(4)


class SourceRefresh(BaseModel):
    target: Literal["all", "gold", "forecast"] = "all"


class DataRefresh(BaseModel):
    target: Literal["all", "gold_links", "gold_status", "forecast_links"] = "all"


@router.get("/settings")
def get_settings():
    return fast_track.status()


def start(kind: str, target: str, user: str, tasks: BackgroundTasks):
    if not fast_track.pdb_ref_sync_configured():
        raise HTTPException(503, "Connessione SSH a lucianavm04 non configurata")
    sources = fast_track.Store().meta("sources")
    if kind == "data" and not sources:
        raise HTTPException(409, "Recupera prima i sorgenti delle dashboard")
    if kind == "sources" and target != "all" and (not sources or sources["source_user"] != fast_track.source_config()["source_user"]):
        raise HTTPException(409, "Recupera entrambe le dashboard per inizializzare questo utente sorgente")
    identifier = fast_track.Store().claim(kind, target, user)
    if not identifier:
        raise HTTPException(409, "Un aggiornamento Fast Track e gia in corso")
    tasks.add_task(fast_track.run_job, identifier, kind, target)
    return fast_track.status()


@router.post("/settings/sources/refresh", status_code=202)
def refresh_sources(body: SourceRefresh, tasks: BackgroundTasks, user: str = Depends(require_fast_track_user)):
    return start("sources", body.target, user, tasks)


@router.post("/settings/data/refresh", status_code=202)
def refresh_data(body: DataRefresh, tasks: BackgroundTasks, user: str = Depends(require_fast_track_user)):
    return start("data", body.target, user, tasks)


@router.get("/content/{revision}/{name:path}")
async def content(revision: str, name: str):
    loop = asyncio.get_running_loop()
    await _file_slots.acquire()
    released = False
    result = None
    def release():
        nonlocal released
        if not released:
            released = True
            loop.call_soon_threadsafe(_file_slots.release)
    try:
        result = await run_in_threadpool(fast_track.publication_file, revision, name)
        # HTML and scripts remain private and revalidate. Never let an intermediary cache user data.
        origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
        if urlsplit(origin).scheme not in {"http", "https"} or any(c in origin for c in "\r\n;' "):
            origin = "https://yellow-forest-0ad79d503.6.azurestaticapps.net"
        headers = {"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff",
                   "Content-Security-Policy": f"frame-ancestors 'self' {origin} https://yellow-forest-0ad79d503.6.azurestaticapps.net"}
        if len(result) == 2:
            release()
            return FileResponse(result[0], media_type=result[1], headers=headers)
        iterator, mime, size, close = result
        def finish():
            close()
            release()
        def stream():
            try:
                yield from iterator
            finally:
                finish()
        headers["Content-Length"] = str(size)
        return StreamingResponse(stream(), media_type=mime, headers=headers, background=BackgroundTask(finish))
    except FileNotFoundError as error:
        release()
        raise HTTPException(404, str(error))
    except Exception:
        if result is not None and len(result) == 4:
            result[3]()
        release()
        raise HTTPException(502, "Lettura dashboard non riuscita; verifica la connessione a lucianavm04")
    except BaseException:
        if result is not None and len(result) == 4:
            result[3]()
        release()
        raise
