from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import requests

from services.mc_code_local_store import mc_code_data_dir, runtime_path


MAX_PAC_AI_BATCH = 100
ACTIVE = {"queued", "analyzing"}


def classification_path() -> Path:
    value = os.getenv("PDB_MC_CLASSIFICATION_LOCAL_PATH", "").strip()
    return Path(value) if value else mc_code_data_dir() / "pdb_mc_classification.parquet"


def classification() -> tuple[str, dict]:
    path = classification_path().resolve()
    stat = path.stat()
    return _classification(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _classification(path: str, _mtime: int, _size: int):
    data = Path(path).read_bytes()
    fields = ("master_code", "family", "subfamily", "product_group", "mc_desc")
    table = pq.read_table(pa.BufferReader(data))
    if not set(fields).issubset(table.column_names):
        raise ValueError("MC Classification priva di codici, descrizioni o note richieste")
    codes = {}
    for row in table.select(fields).to_pylist():
        row = {key: str(value or "").strip() for key, value in row.items()}
        code = row["master_code"]
        if not re.fullmatch(r"\d{2}_\d{2}_\d{2}", code):
            continue
        if code in codes and codes[code] != row:
            raise ValueError(f"Master Code duplicato con descrizioni discordanti: {code}")
        codes[code] = row
    if not codes:
        raise ValueError("MC Classification senza Master Code validi")
    return hashlib.sha256(data).hexdigest(), codes


class PacAiWorkerError(RuntimeError):
    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


class PacAiWorkerClient:
    def __init__(self):
        self.url = (os.getenv("PAC_AI_WORKER_URL") or os.getenv("BS25AI_WORKER_URL") or "").strip().rstrip("/")
        self.token = (os.getenv("PAC_AI_WORKER_TOKEN") or os.getenv("BS25AI_WORKER_TOKEN") or "").strip()
        if not self.url or not self.token:
            raise PacAiWorkerError("Collegamento PAC-AI a lucianavm04 non configurato")

    def _post(self, endpoint: str, body: dict) -> list[dict]:
        response = requests.post(self.url + endpoint, json=body,
                                 headers={"Authorization": f"Bearer {self.token}"}, timeout=(3, 15))
        if not response.ok:
            try:
                detail = str(response.json().get("detail", ""))[:500]
            except ValueError:
                detail = response.text[:500]
            raise PacAiWorkerError(f"Worker PAC-AI HTTP {response.status_code}: {detail}",
                                   permanent=response.status_code in {400, 401, 403, 409, 422})
        result = response.json()
        if not isinstance(result, dict) or not isinstance(result.get("jobs"), list):
            raise PacAiWorkerError("Risposta worker PAC-AI non valida")
        expected = set(body.get("request_ids", [])) or {j["request_id"] for j in body["jobs"]}
        seen = set()
        for job in result["jobs"]:
            if (not isinstance(job, dict) or job.get("request_id") not in expected
                    or job["request_id"] in seen or job.get("status") not in ACTIVE | {"completed", "failed"}):
                raise PacAiWorkerError("Risposta worker PAC-AI con job inatteso o duplicato")
            seen.add(job["request_id"])
        return result["jobs"]

    def submit(self, jobs: list[dict]) -> list[dict]:
        return self._post("/v1/pac-ai/jobs", {"jobs": jobs})

    def status(self, request_ids: list[str]) -> list[dict]:
        return self._post("/v1/pac-ai/status", {"request_ids": request_ids})


def pac_ai_configuration() -> dict:
    try:
        PacAiWorkerClient()
        version, codes = classification()
        return {"available": True, "message": None, "taxonomy_version": version,
                "master_codes": len(codes), "max_batch_size": MAX_PAC_AI_BATCH}
    except (PacAiWorkerError, OSError, ValueError) as exc:
        return {"available": False, "message": str(exc), "max_batch_size": MAX_PAC_AI_BATCH}


def _text(value: Any) -> str:
    if isinstance(value, list):
        return next((text for v in value if (text := _text(v))), "")
    return str(value or "").strip()


def worker_item(item: dict) -> dict:
    # Whitelist source attributes. Neither other classifiers nor saved MC proposals are evidence.
    extras = item.get("item_extra_descriptions") or {}
    if isinstance(extras, str):
        try:
            extras = json.loads(extras)
        except ValueError:
            extras = {}
    fields = ("manufacturer", "brand_raw", "brand", "brand_prefix", "prefix_code", "father_name",
              "pack", "inner_count", "inner_qty", "pack_measure_unit", "measure", "feature")
    details = {key: item[key] for key in fields if item.get(key) is not None}
    if isinstance(extras, dict):
        details["item_extra_descriptions"] = {key: value for key, value in extras.items()
                                              if key in fields or key in {"description", "product_description", "material"}}
    return {"company": item["company"], "item_code": item["item_code"],
            "company_item_code": item.get("company_item_code"), "description": item["description"],
            "brand": _text(item.get("brand")) or _text(item.get("brand_raw")), "extra": details}


class PacAiStore:
    def __init__(self, path: Path | None = None):
        self.path = path or runtime_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS pac_ai_jobs (
                environment TEXT NOT NULL, company TEXT NOT NULL COLLATE NOCASE, item_code TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL, status TEXT NOT NULL,
                stage TEXT NOT NULL, result_json TEXT, thread_id TEXT, error_message TEXT,
                requested_by TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                PRIMARY KEY(environment, company, item_code))""")

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def create(self, environment: str, item: dict, version: str, actor: str) -> str | None:
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            key = (environment, item["company"], item["item_code"])
            previous = c.execute("SELECT status FROM pac_ai_jobs WHERE environment=? AND company=? AND item_code=?", key).fetchone()
            if previous and previous["status"] != "failed":
                return None
            request_id = uuid4().hex
            payload = {"request_id": request_id, "taxonomy_version": version, "item": worker_item(item)}
            now = time.time()
            c.execute("""INSERT INTO pac_ai_jobs(environment,company,item_code,request_id,payload_json,status,stage,
                         requested_by,created_at,updated_at) VALUES (?,?,?,?,?,'queued','queued',?,?,?)
                         ON CONFLICT(environment,company,item_code) DO UPDATE SET
                         request_id=excluded.request_id,payload_json=excluded.payload_json,status='queued',stage='queued',
                         result_json=NULL,thread_id=NULL,error_message=NULL,requested_by=excluded.requested_by,
                         created_at=excluded.created_at,updated_at=excluded.updated_at""",
                      (*key, request_id, json.dumps(payload, ensure_ascii=False), actor, now, now))
        return request_id

    def active(self, environment: str, company: str) -> list[dict]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM pac_ai_jobs WHERE environment=? AND company=? "
                             "AND status IN ('queued','analyzing') ORDER BY updated_at LIMIT ?",
                             (environment, company, MAX_PAC_AI_BATCH)).fetchall()
        return [dict(row) for row in rows]

    def update(self, request_id: str, **values):
        values = {key: value for key, value in values.items() if key in
                  {"status", "stage", "result_json", "thread_id", "error_message"}}
        values["updated_at"] = time.time()
        with self.connect() as c:
            c.execute(f"UPDATE pac_ai_jobs SET {','.join(k+'=?' for k in values)} WHERE request_id=? "
                      "AND status IN ('queued','analyzing')",
                      [*values.values(), request_id])

    def enrich(self, environment: str, company: str, rows: list[dict]):
        if not rows:
            return
        codes = [r["item_code"] for r in rows]
        with self.connect() as c:
            jobs = c.execute(f"SELECT * FROM pac_ai_jobs WHERE environment=? AND company=? "
                             f"AND item_code IN ({','.join('?' for _ in codes)})", [environment, company, *codes]).fetchall()
        by_code = {r["item_code"]: r for r in jobs}
        for row in rows:
            job = by_code.get(row["item_code"])
            if job:
                result = json.loads(job["result_json"]) if job["result_json"] else None
                row.update(pac_ai_status=job["status"], pac_ai_stage=job["stage"], pac_ai_result=result,
                           pac_ai_error_message=job["error_message"], pac_ai_request_id=job["request_id"])


def validate_result(result: Any, expected_version: str) -> dict:
    version, codes = classification()
    if version != expected_version or not isinstance(result, dict) or result.get("taxonomy_version") != version:
        raise ValueError("Reference MC Classification cambiata o risultato non coerente: ripetere PAC-AI")
    if result.get("decision") not in {"match", "ambiguous", "unresolved"}:
        raise ValueError("Decisione PAC-AI non valida")
    code = result.get("master_code")
    initial = result.get("initial_master_code")
    if (code is not None and code not in codes) or (initial is not None and initial not in codes):
        raise ValueError("Master Code PAC-AI assente dalla classificazione corrente")
    if result["decision"] == "match" and not code:
        raise ValueError("Match PAC-AI senza Master Code")
    if result.get("confidence") not in {"high", "medium", "low"} or not isinstance(result.get("rationale"), str):
        raise ValueError("Affidabilita o motivazione PAC-AI non valida")
    if not isinstance(result.get("evidence"), list) or any(
        not isinstance(e, dict) or not e.get("pdb_ref") or e.get("master_code") not in codes for e in result["evidence"]
    ):
        raise ValueError("Evidenze PDB PAC-AI non valide")
    return {**result, "classification": codes.get(code, {}),
            "review_outcome": "unresolved" if result["decision"] != "match" else
                              "confirmed" if code == initial else "corrected"}


def sync_pac_ai(environment: str, company: str, worker=None) -> dict:
    """Short status calls; resubmit missing IDs to recover interrupted backend dispatch."""
    store = PacAiStore()
    jobs = store.active(environment, company)
    if not jobs:
        return {"active": False, "updated": 0, "error_message": None}
    try:
        client = worker or PacAiWorkerClient()
        remote = client.status([j["request_id"] for j in jobs])
        found = {j["request_id"] for j in remote}
        missing = [json.loads(j["payload_json"]) for j in jobs if j["request_id"] not in found]
        if missing:
            remote.extend(client.submit(missing))
        expected = {j["request_id"]: j for j in jobs}
        for job in remote:
            local = expected.get(job["request_id"])
            if local is None:
                raise ValueError("Job PAC-AI inatteso")
            values = {key: job.get(key) for key in ("status", "stage", "thread_id", "error_message")}
            if job["status"] == "completed":
                try:
                    result = validate_result(job.get("result"), json.loads(local["payload_json"])["taxonomy_version"])
                    values["result_json"] = json.dumps(result, ensure_ascii=False)
                except (ValueError, OSError) as exc:
                    values.update(status="failed", stage="failed", error_message=str(exc))
            store.update(job["request_id"], **values)
        return {"active": bool(store.active(environment, company)), "updated": len(remote), "error_message": None}
    except Exception as exc:
        permanent = isinstance(exc, PacAiWorkerError) and exc.permanent
        for job in jobs:
            values = {"error_message": str(exc)[:1000]}
            if permanent:
                values.update(status="failed", stage="failed")
            store.update(job["request_id"], **values)
        return {"active": not permanent, "updated": len(jobs), "error_message": str(exc)[:1000]}
