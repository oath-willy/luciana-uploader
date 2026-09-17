from __future__ import annotations

import os
import shlex
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import paramiko
import pyarrow.parquet as pq
from azure.core import MatchConditions
from azure.core.exceptions import HttpResponseError

from services.mc_code_local_store import mc_code_data_dir
from services.pdb_ref_sync import (
    PdbRefSyncError, PdbRefSyncStore, _run_remote, connect_vm04,
    pdb_ref_sync_configured, utc_now,
)
from services.pdb_storage import ACCOUNT_NAME, CONTAINER_NAME, blob_client


FILE_NAME = "pdb_mc_classification.parquet"
MAX_FILE_BYTES = 5 * 1024 * 1024 * 1024
DEFAULT_REMOTE_PATH = (
    "/home/lucianauser/panel_data_utilities/scripts/jobs/pdb/"
    + FILE_NAME
)


def classification_path() -> Path:
    configured = os.getenv("PDB_MC_CLASSIFICATION_LOCAL_PATH", "").strip()
    return Path(configured).expanduser() if configured else mc_code_data_dir() / FILE_NAME


def classification_job_store() -> PdbRefSyncStore:
    configured = os.getenv("PDB_MC_CLASSIFICATION_STATUS_DB", "").strip()
    path = Path(configured).expanduser() if configured else mc_code_data_dir() / "pdb-mc-classification-sync.sqlite3"
    return PdbRefSyncStore(path)


def classification_status() -> dict[str, Any]:
    path = classification_path()
    stat = path.stat() if path.is_file() else None
    job = classification_job_store().get()
    return {
        "configured": pdb_ref_sync_configured(),
        "source": f"{ACCOUNT_NAME}/{CONTAINER_NAME}/{FILE_NAME}",
        "remote_path": os.getenv("PDB_MC_CLASSIFICATION_REMOTE_PATH", DEFAULT_REMOTE_PATH).strip(),
        "file": {
            "available": stat is not None,
            "name": FILE_NAME,
            "size_bytes": stat.st_size if stat else None,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
        },
        "job": job,
        "copies": {
            "backend": None if not job or job.get("backend_copy_ok") is None else bool(job["backend_copy_ok"]),
            "vm04": None if not job or job.get("vm_copy_ok") is None else bool(job["vm_copy_ok"]),
        },
    }


def _blob_client():
    connection_env = (
        "PDB_MC_CLASSIFICATION_STORAGE_CONNECTION_STRING"
        if os.getenv("PDB_MC_CLASSIFICATION_STORAGE_CONNECTION_STRING", "").strip()
        else "PDB_NEW_ITEMS_STORAGE_CONNECTION_STRING"
    )
    secret_env = (
        "PDB_MC_CLASSIFICATION_STORAGE_SECRET"
        if os.getenv("PDB_MC_CLASSIFICATION_STORAGE_SECRET", "").strip()
        else "PDB_NEW_ITEMS_STORAGE_SECRET"
    )
    return blob_client(
        FILE_NAME,
        connection_env,
        secret_env,
    )


def _publish_to_vm(client: paramiko.SSHClient, local_path: Path, remote_path: str) -> None:
    temporary = f"{remote_path}.{uuid4().hex}.tmp"
    sftp = client.open_sftp()
    try:
        with local_path.open("rb") as source, sftp.file(temporary, "wb") as destination:
            while block := source.read(4 * 1024 * 1024):
                destination.write(block)
            destination.flush()
        remote_size = int(sftp.stat(temporary).st_size)
        if remote_size != local_path.stat().st_size:
            raise PdbRefSyncError(
                f"Copia su lucianavm04 incompleta: {remote_size} byte su {local_path.stat().st_size}"
            )
        _run_remote(
            client,
            f"mv -f -- {shlex.quote(temporary)} {shlex.quote(remote_path)}",
            int(os.getenv("PDB_MC_CLASSIFICATION_VM_TIMEOUT_SECONDS", "3600")),
        )
    finally:
        try:
            sftp.remove(temporary)
        except OSError:
            pass
        sftp.close()


def run_classification_sync(request_id: str) -> None:
    store = classification_job_store()
    store.update(request_id, status="running", stage="downloading", started_at=utc_now())
    target = classification_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    client: paramiko.SSHClient | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".pdb-mc-classification-", suffix=".parquet", dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        with _blob_client() as blob:
            properties = blob.get_blob_properties()
            expected_size = int(properties.size)
            if expected_size <= 8 or expected_size > MAX_FILE_BYTES:
                raise PdbRefSyncError("Dimensione del Parquet MC Classification non valida")
            with temporary.open("wb") as destination:
                blob.download_blob(
                    etag=properties.etag,
                    match_condition=MatchConditions.IfNotModified,
                ).readinto(destination)
                destination.flush()
                os.fsync(destination.fileno())
        if temporary.stat().st_size != expected_size:
            raise PdbRefSyncError("Download MC Classification incompleto")
        with pq.ParquetFile(temporary) as parquet:
            row_count = parquet.metadata.num_rows
            column_count = parquet.metadata.num_columns

        store.update(
            request_id, stage="uploading", remote_size_bytes=expected_size,
            local_size_bytes=expected_size, row_count=row_count, column_count=column_count,
        )
        client = connect_vm04()
        remote_path = os.getenv("PDB_MC_CLASSIFICATION_REMOTE_PATH", DEFAULT_REMOTE_PATH).strip()
        _publish_to_vm(client, temporary, remote_path)
        store.update(request_id, vm_copy_ok=True)
        os.replace(temporary, target)
        store.update(request_id, backend_copy_ok=True)
        store.update(
            request_id, status="completed", stage="completed",
            completed_at=utc_now(), error_message=None, backend_copy_ok=True,
        )
    except Exception as exc:
        message = (
            f"Accesso Azure Storage non riuscito ({exc.status_code}). Verificare Storage Blob Data Reader."
            if isinstance(exc, HttpResponseError) else str(exc)
        )
        job = store.get() or {}
        store.update(
            request_id, status="failed", stage="failed",
            completed_at=utc_now(), error_message=message[:2000],
            backend_copy_ok=False if job.get("backend_copy_ok") is None else job.get("backend_copy_ok"),
            vm_copy_ok=False if job.get("vm_copy_ok") is None else job.get("vm_copy_ok"),
        )
    finally:
        if client is not None:
            client.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
