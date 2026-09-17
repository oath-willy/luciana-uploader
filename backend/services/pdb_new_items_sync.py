from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pyarrow.parquet as pq
from azure.core import MatchConditions
from azure.core.exceptions import HttpResponseError

from services.mc_code_local_store import (
    MAX_EXTRA_COLUMNS, McCodeSnapshotStore, SnapshotValidationError,
    mc_code_data_dir, publish_snapshot, snapshot_path,
)
from services.pdb_ref_sync import PdbRefSyncStore, utc_now
from services.pdb_storage import ACCOUNT_NAME, CONTAINER_NAME, blob_client


FILE_NAME = "pdb_new_items.parquet"
MAX_FILE_BYTES = 5 * 1024 * 1024 * 1024
CORE_FIELDS = {"company", "item_code", "company_item_code", "description"}
JSON_FIELD = "item_extra_descriptions"


def new_items_path() -> Path:
    return mc_code_data_dir() / FILE_NAME


def new_items_job_store() -> PdbRefSyncStore:
    return PdbRefSyncStore(mc_code_data_dir() / "pdb-new-items-sync.sqlite3")


def new_items_status() -> dict[str, Any]:
    path = new_items_path()
    stat = path.stat() if path.is_file() else None
    job = new_items_job_store().get()
    return {
        "configured": True,
        "source": f"{ACCOUNT_NAME}/{CONTAINER_NAME}/{FILE_NAME}",
        "file": {
            "available": stat is not None,
            "name": FILE_NAME,
            "size_bytes": stat.st_size if stat else None,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
        },
        "job": job,
        "copies": {"backend": None if not job or job.get("backend_copy_ok") is None else bool(job["backend_copy_ok"])},
    }


def _blob_client():
    return blob_client(
        FILE_NAME,
        "PDB_NEW_ITEMS_STORAGE_CONNECTION_STRING",
        "PDB_NEW_ITEMS_STORAGE_SECRET",
    )


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _record(raw: dict[str, Any]) -> dict[str, Any]:
    raw = _normalize_value(raw)
    company = str(raw.get("company") or "").strip().upper()
    item_code = str(raw.get("item_code") or "").strip()
    if not company or not item_code:
        raise SnapshotValidationError("New Items richiede company e item_code non vuoti")
    details = {key: value for key, value in raw.items() if key not in CORE_FIELDS}
    extra = details.get(JSON_FIELD)
    if isinstance(extra, str):
        try:
            extra = json.loads(extra) if extra.strip() else {}
        except json.JSONDecodeError as exc:
            raise SnapshotValidationError(f"JSON non valido per {company}|{item_code}") from exc
    if extra is not None and not isinstance(extra, dict):
        raise SnapshotValidationError(f"{JSON_FIELD} deve contenere un oggetto JSON")
    details[JSON_FIELD] = extra or {}
    # Keep the original JSON and expose its fields to the existing full-view grid.
    for key, value in (extra or {}).items():
        if key in CORE_FIELDS or key.startswith(("bs25_", "aibs25_")) or key == "id":
            continue
        details.setdefault(key, value)
    return {
        "company": company, "item_code": item_code,
        "company_item_code": f"{company}|{item_code}",
        "description": raw.get("description"), "details": details,
    }


def _records(parquet: pq.ParquetFile) -> Iterator[dict[str, Any]]:
    for batch in parquet.iter_batches(batch_size=500):
        for raw in batch.to_pylist():
            yield _record(raw)


def build_new_items_snapshot(parquet_path: Path, target: Path, snapshot_id: str) -> dict[str, Any]:
    with pq.ParquetFile(parquet_path) as parquet:
        if not {"company", "item_code", "description"}.issubset(parquet.schema_arrow.names):
            raise SnapshotValidationError("New Items richiede le colonne company, item_code e description")
        fields: dict[str, dict[str, str]] = {}
        for item in _records(parquet):
            columns = fields.setdefault(item["company"], {})
            for key, value in item["details"].items():
                if key == JSON_FIELD:
                    continue
                value_type = "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "string"
                columns.setdefault(key, value_type)
        companies = [
            {
                "company": company, "full_view_available": True,
                "extra_columns": [
                    {"field": key, "header_name": key.replace("_", " ").title(), "value_type": value_type}
                    for key, value_type in columns.items()
                ][:MAX_EXTRA_COLUMNS],
            }
            for company, columns in sorted(fields.items())
        ]
        previous = McCodeSnapshotStore("dev")
        if not previous.path.is_file():
            raise SnapshotValidationError("Reference canonica assente: pubblicare prima lo snapshot MC CODE iniziale")
        result = publish_snapshot(
            "dev", snapshot_id, utc_now(), companies, _records(parquet),
            previous.all_master_codes(), target_path=target,
        )
    # Retain imported lookup results; runtime jobs and operator choices are separate.
    with closing(sqlite3.connect(target)) as connection:
        connection.execute("ATTACH DATABASE ? AS previous", (str(previous.path),))
        fields_to_copy = "bs25_status, proposal_1_json, proposal_2_json, proposal_3_json, selected_proposal_rank, selected_master_code, selection_status"
        connection.execute(
            f"UPDATE items SET ({fields_to_copy}) = "
            f"(SELECT {fields_to_copy} FROM previous.items p WHERE p.company = items.company AND p.item_code = items.item_code) "
            "WHERE EXISTS (SELECT 1 FROM previous.items p WHERE p.company = items.company AND p.item_code = items.item_code)"
        )
        connection.execute("INSERT OR REPLACE INTO metadata VALUES ('source_file', ?)", (FILE_NAME,))
        connection.commit()
    return result


def run_new_items_sync(request_id: str) -> None:
    store = new_items_job_store()
    store.update(request_id, status="running", stage="downloading", started_at=utc_now())
    temporary: Path | None = None
    staged_snapshot: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".pdb-new-items-", suffix=".parquet", dir=mc_code_data_dir())
        os.close(descriptor)
        temporary = Path(temporary_name)
        with _blob_client() as blob:
            properties = blob.get_blob_properties()
            expected_size = properties.size
            if expected_size <= 8 or expected_size > MAX_FILE_BYTES:
                raise SnapshotValidationError("Dimensione del Parquet New Items non valida")
            with temporary.open("wb") as destination:
                blob.download_blob(etag=properties.etag, match_condition=MatchConditions.IfNotModified).readinto(destination)
                destination.flush()
                os.fsync(destination.fileno())
        if temporary.stat().st_size != expected_size:
            raise SnapshotValidationError("Download New Items incompleto")
        store.update(request_id, stage="indexing", remote_size_bytes=expected_size)
        descriptor, snapshot_name = tempfile.mkstemp(prefix=".new-items-snapshot-", suffix=".sqlite3", dir=mc_code_data_dir())
        os.close(descriptor)
        staged_snapshot = Path(snapshot_name)
        result = build_new_items_snapshot(temporary, staged_snapshot, f"{FILE_NAME}:{properties.etag}")
        with pq.ParquetFile(temporary) as parquet:
            column_count = len(parquet.schema_arrow.names)
        os.replace(temporary, new_items_path())
        store.update(request_id, backend_copy_ok=True)
        os.replace(staged_snapshot, snapshot_path("dev"))
        store.update(
            request_id, status="completed", stage="completed", completed_at=utc_now(),
            local_size_bytes=expected_size, row_count=result["rows"], column_count=column_count,
            backend_copy_ok=True,
        )
    except Exception as exc:
        if isinstance(exc, HttpResponseError):
            message = f"Accesso Azure Storage non riuscito ({exc.status_code}). Verificare Storage Blob Data Reader o la connection string dedicata."
        else:
            message = str(exc)[:1000]
        job = store.get() or {}
        store.update(
            request_id, status="failed", stage="failed", error_message=message,
            completed_at=utc_now(),
            backend_copy_ok=False if job.get("backend_copy_ok") is None else job.get("backend_copy_ok"),
        )
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        if staged_snapshot:
            staged_snapshot.unlink(missing_ok=True)
