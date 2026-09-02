from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from codex_app_server import CodexAppServer, CodexAppServerError
from prompts import RESULT_SCHEMA, build_goal, build_prompt, validate_bundle, write_case


class ReviewRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    mode: Literal["low", "xhigh"]
    thread_id: str | None = None
    item: dict[str, Any]
    proposals: list[dict[str, Any]] = Field(min_length=3, max_length=3)
    taxonomy_coherent: bool
    routing_flag: str | None = None
    canonical_master_codes: list[dict[str, Any]] = Field(default_factory=list)


class GoalRequest(BaseModel):
    thread_id: str = Field(min_length=1)


app = FastAPI(title="Luciana BS25AI worker", version="1.0.0")


@app.get("/health")
def health():
    bundle_dir = _bundle_dir()
    try:
        validate_bundle(bundle_dir)
        bundle = "ready"
    except ValueError as exc:
        bundle = str(exc)
    return {"status": "ok", "bundle": bundle, "codex_user": os.getenv("USER")}


@app.post("/v1/reviews")
def review(payload: ReviewRequest, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    bundle_dir = _bundle_dir()
    try:
        validate_bundle(bundle_dir)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if payload.mode == "xhigh" and not payload.thread_id:
        raise HTTPException(status_code=400, detail="xhigh richiede il thread Sol low")
    if payload.mode == "xhigh" and not payload.canonical_master_codes:
        raise HTTPException(status_code=400, detail="Reference Master Code canonica assente")

    with tempfile.TemporaryDirectory(prefix="bs25ai-") as temporary_name:
        work_dir = Path(temporary_name)
        case_path = work_dir / "case.json"
        master_codes_path = work_dir / "master_codes.json"
        write_case(
            case_path,
            {
                "request_id": payload.request_id,
                "item": payload.item,
                "proposals": payload.proposals,
                "taxonomy_coherent": payload.taxonomy_coherent,
                "routing_flag": payload.routing_flag,
            },
        )
        if payload.mode == "xhigh":
            write_case(master_codes_path, {"master_codes": payload.canonical_master_codes})

        try:
            with CodexAppServer(
                executable=os.getenv("CODEX_EXECUTABLE", "codex"),
                timeout_seconds=int(os.getenv("BS25AI_CODEX_TIMEOUT_SECONDS", "900")),
            ) as codex:
                if payload.thread_id:
                    thread_id = payload.thread_id
                    codex.resume_thread(thread_id, work_dir)
                else:
                    thread_id = codex.start_thread(work_dir)
                    codex.set_goal(thread_id, build_goal(payload.item), "active")
                result = codex.run_turn(
                    thread_id,
                    build_prompt(
                        payload.mode,
                        case_path,
                        bundle_dir,
                        master_codes_path if payload.mode == "xhigh" else None,
                    ),
                    RESULT_SCHEMA,
                    "low" if payload.mode == "low" else "xhigh",
                    payload.mode == "xhigh",
                )
                final_status = (
                    "complete"
                    if payload.mode == "xhigh" or result.get("decision") == "match"
                    else "paused"
                )
                codex.set_goal(thread_id, build_goal(payload.item), final_status)
        except (CodexAppServerError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"thread_id": thread_id, "result": result}


@app.post("/v1/goals/complete")
def complete_goal(payload: GoalRequest, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    try:
        with CodexAppServer(
            executable=os.getenv("CODEX_EXECUTABLE", "codex"),
            timeout_seconds=60,
        ) as codex:
            codex.set_goal_status(payload.thread_id, "complete")
    except CodexAppServerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"thread_id": payload.thread_id, "goal_status": "complete"}


def _authorize(authorization: str | None) -> None:
    expected = os.getenv("BS25AI_WORKER_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="BS25AI_WORKER_TOKEN non configurato")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Token worker non valido")


def _bundle_dir() -> Path:
    configured = os.getenv("BS25AI_HANDOVER_DIR", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="BS25AI_HANDOVER_DIR non configurato")
    return Path(configured).expanduser().resolve()
