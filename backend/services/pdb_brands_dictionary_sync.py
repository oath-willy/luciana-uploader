from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from azure.core import MatchConditions
from azure.core.exceptions import HttpResponseError

from services.mc_code_local_store import mc_code_data_dir
from services.pdb_ref_sync import PdbRefSyncError, PdbRefSyncStore, utc_now
from services.pdb_storage import ACCOUNT_NAME, CONTAINER_NAME, blob_client


FILE_NAME = "pdb_brands_dictionary.parquet"
MAX_FILE_BYTES = 5 * 1024 * 1024 * 1024


def brands_dictionary_path() -> Path:
    configured = os.getenv("PDB_BRANDS_DICTIONARY_LOCAL_PATH", "").strip()
    return Path(configured).expanduser() if configured else mc_code_data_dir() / FILE_NAME


def brands_dictionary_job_store() -> PdbRefSyncStore:
    configured = os.getenv("PDB_BRANDS_DICTIONARY_STATUS_DB", "").strip()
    path = (
        Path(configured).expanduser()
        if configured
        else mc_code_data_dir() / "pdb-brands-dictionary-sync.sqlite3"
    )
    return PdbRefSyncStore(path)


def brands_dictionary_status() -> dict[str, Any]:
    path = brands_dictionary_path()
    stat = path.stat() if path.is_file() else None
    job = brands_dictionary_job_store().get()
    return {
        "configured": True,
        "source": f"{ACCOUNT_NAME}/{CONTAINER_NAME}/{FILE_NAME}",
        "file": {
            "available": stat is not None,
            "name": FILE_NAME,
            "size_bytes": stat.st_size if stat else None,
            "modified_at": (
                datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                if stat else None
            ),
        },
        "job": job,
        "copies": {
            "backend": (
                None
                if not job or job.get("backend_copy_ok") is None
                else bool(job["backend_copy_ok"])
            ),
        },
    }


def _blob_client():
    connection_env = (
        "PDB_BRANDS_DICTIONARY_STORAGE_CONNECTION_STRING"
        if os.getenv("PDB_BRANDS_DICTIONARY_STORAGE_CONNECTION_STRING", "").strip()
        else "PDB_NEW_ITEMS_STORAGE_CONNECTION_STRING"
    )
    secret_env = (
        "PDB_BRANDS_DICTIONARY_STORAGE_SECRET"
        if os.getenv("PDB_BRANDS_DICTIONARY_STORAGE_SECRET", "").strip()
        else "PDB_NEW_ITEMS_STORAGE_SECRET"
    )
    return blob_client(FILE_NAME, connection_env, secret_env)


def run_brands_dictionary_sync(request_id: str) -> None:
    store = brands_dictionary_job_store()
    store.update(
        request_id,
        status="running",
        stage="downloading",
        started_at=utc_now(),
    )
    target = brands_dictionary_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".pdb-brands-dictionary-",
            suffix=".parquet",
            dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)

        with _blob_client() as blob:
            properties = blob.get_blob_properties()
            expected_size = int(properties.size)
            if expected_size <= 8 or expected_size > MAX_FILE_BYTES:
                raise PdbRefSyncError("Dimensione del Parquet Brands Dictionary non valida")
            with temporary.open("wb") as destination:
                blob.download_blob(
                    etag=properties.etag,
                    match_condition=MatchConditions.IfNotModified,
                ).readinto(destination)
                destination.flush()
                os.fsync(destination.fileno())

        if temporary.stat().st_size != expected_size:
            raise PdbRefSyncError("Download Brands Dictionary incompleto")

        with pq.ParquetFile(temporary) as parquet:
            row_count = parquet.metadata.num_rows
            column_count = parquet.metadata.num_columns

        os.replace(temporary, target)
        store.update(
            request_id,
            status="completed",
            stage="completed",
            completed_at=utc_now(),
            error_message=None,
            remote_size_bytes=expected_size,
            local_size_bytes=expected_size,
            row_count=row_count,
            column_count=column_count,
            backend_copy_ok=True,
        )
    except Exception as exc:
        message = (
            "Accesso Azure Storage non riuscito "
            f"({exc.status_code}). Verificare Storage Blob Data Reader."
            if isinstance(exc, HttpResponseError)
            else str(exc)
        )
        job = store.get() or {}
        store.update(
            request_id,
            status="failed",
            stage="failed",
            completed_at=utc_now(),
            error_message=message[:2000],
            backend_copy_ok=(
                False
                if job.get("backend_copy_ok") is None
                else job.get("backend_copy_ok")
            ),
        )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
