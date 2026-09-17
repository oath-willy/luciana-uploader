from __future__ import annotations

import io
import json
import os
import shlex
import shutil
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import paramiko
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from services.mc_code_local_store import mc_code_data_dir


REMOTE_FETCH_SCRIPT = (
    "/home/lucianauser/panel_data_utilities/scripts/jobs/pdb/fetch_ref_pdb_dump.sh"
)
REMOTE_PARQUET = (
    "/home/lucianauser/panel_data_utilities/scripts/jobs/pdb/ref_pdb_dump.parquet"
)
REMOTE_INDEX_PYTHON = (
    "/home/lucianauser/panel_data_utilities/functions/pdb/.venv/bin/python"
)
REMOTE_INDEX_SCRIPT = (
    "/home/lucianauser/panel_data_utilities/functions/pdb/build_index.py"
)
MAX_PARQUET_BYTES = 5 * 1024 * 1024 * 1024
ACTIVE_STATES = {"queued", "running"}
_SCHEMA_LOCK = threading.Lock()


class PdbRefSyncError(RuntimeError):
    pass


def pdb_ref_local_path() -> Path:
    configured = os.getenv("PDB_REF_LOCAL_PATH", "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else mc_code_data_dir() / "ref_pdb_dump.parquet"
    )


def pdb_ref_status_path() -> Path:
    configured = os.getenv("PDB_REF_STATUS_DB", "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else mc_code_data_dir() / "pdb-settings.sqlite3"
    )


class PdbRefSyncStore:
    def __init__(self, path: Path | None = None):
        self.path = path or pdb_ref_status_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def claim(self, request_id: str, requested_by: str) -> bool:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT status, updated_at FROM pdb_ref_sync WHERE singleton=1"
            ).fetchone()
            if existing and existing["status"] in ACTIVE_STATES:
                if not _is_stale(existing["updated_at"]):
                    connection.rollback()
                    return False
            connection.execute(
                """
                INSERT INTO pdb_ref_sync (
                    singleton, request_id, status, stage, requested_by,
                    requested_at, started_at, completed_at, updated_at,
                    error_message, remote_size_bytes, local_size_bytes,
                    row_count, column_count, document_count, retriever_version,
                    backend_copy_ok, vm_copy_ok
                ) VALUES (1, ?, 'queued', 'queued', ?, ?, NULL, NULL, ?,
                    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
                ON CONFLICT(singleton) DO UPDATE SET
                    request_id=excluded.request_id,
                    status='queued',
                    stage='queued',
                    requested_by=excluded.requested_by,
                    requested_at=excluded.requested_at,
                    started_at=NULL,
                    completed_at=NULL,
                    updated_at=excluded.updated_at,
                    error_message=NULL,
                    remote_size_bytes=NULL,
                    local_size_bytes=NULL,
                    row_count=NULL,
                    column_count=NULL,
                    document_count=NULL,
                    retriever_version=NULL,
                    backend_copy_ok=NULL,
                    vm_copy_ok=NULL
                """,
                (request_id, requested_by, now, now),
            )
            connection.commit()
        return True

    def update(self, request_id: str, **values: Any) -> None:
        allowed = {
            "status",
            "stage",
            "started_at",
            "completed_at",
            "error_message",
            "remote_size_bytes",
            "local_size_bytes",
            "row_count",
            "column_count",
            "document_count",
            "retriever_version",
            "backend_copy_ok",
            "vm_copy_ok",
        }
        payload = {key: value for key, value in values.items() if key in allowed}
        if not payload:
            return
        payload["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in payload)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE pdb_ref_sync SET {assignments} "
                "WHERE singleton=1 AND request_id=?",
                [*payload.values(), request_id],
            )
            connection.commit()

    def get(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pdb_ref_sync WHERE singleton=1"
            ).fetchone()
        if row is None:
            return None
        return {key: row[key] for key in row.keys() if key != "singleton"}

    def _initialize(self) -> None:
        with _SCHEMA_LOCK, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pdb_ref_sync (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    request_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    error_message TEXT,
                    remote_size_bytes INTEGER,
                    local_size_bytes INTEGER,
                    row_count INTEGER,
                    column_count INTEGER,
                    document_count INTEGER,
                    retriever_version TEXT,
                    backend_copy_ok INTEGER,
                    vm_copy_ok INTEGER
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(pdb_ref_sync)")}
            for name in ("backend_copy_ok", "vm_copy_ok"):
                if name not in columns:
                    connection.execute(f"ALTER TABLE pdb_ref_sync ADD COLUMN {name} INTEGER")
            connection.execute(
                "UPDATE pdb_ref_sync SET backend_copy_ok=1 WHERE status='completed' AND backend_copy_ok IS NULL"
            )
            connection.execute(
                "UPDATE pdb_ref_sync SET vm_copy_ok=1 WHERE status='completed' AND vm_copy_ok IS NULL"
            )
            connection.commit()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()


def run_pdb_ref_sync(request_id: str) -> None:
    store = PdbRefSyncStore()
    store.update(
        request_id,
        status="running",
        stage="fetching",
        started_at=utc_now(),
        error_message=None,
    )
    client: paramiko.SSHClient | None = None
    try:
        client = _connect_vm04()
        fetch_output = _run_remote(
            client,
            shlex.quote(os.getenv("PDB_REF_FETCH_SCRIPT", REMOTE_FETCH_SCRIPT)),
            int(os.getenv("PDB_REF_FETCH_TIMEOUT_SECONDS", "3600")),
        )
        fetch_metadata = _parse_key_values(fetch_output)
        store.update(request_id, vm_copy_ok=True)

        remote_path = os.getenv("PDB_REF_REMOTE_PATH", REMOTE_PARQUET).strip()
        store.update(request_id, stage="downloading")
        local_size, remote_size = _download_parquet(client, remote_path)
        store.update(
            request_id,
            stage="indexing",
            backend_copy_ok=True,
            remote_size_bytes=remote_size,
            local_size_bytes=local_size,
            row_count=_integer_or_none(fetch_metadata.get("ROWS")),
            column_count=_integer_or_none(fetch_metadata.get("COLUMNS")),
        )

        index_python = os.getenv("PDB_REF_INDEX_PYTHON", REMOTE_INDEX_PYTHON).strip()
        index_script = os.getenv("PDB_REF_INDEX_SCRIPT", REMOTE_INDEX_SCRIPT).strip()
        index_output = _run_remote(
            client,
            f"{shlex.quote(index_python)} {shlex.quote(index_script)}",
            int(os.getenv("PDB_REF_INDEX_TIMEOUT_SECONDS", "7200")),
        )
        index_metadata = _parse_json_line(index_output)
        store.update(
            request_id,
            status="completed",
            stage="completed",
            completed_at=utc_now(),
            document_count=_integer_or_none(index_metadata.get("document_count")),
            retriever_version=str(index_metadata.get("retriever_version") or "") or None,
            error_message=None,
        )
    except Exception as exc:
        job = store.get() or {}
        store.update(
            request_id,
            status="failed",
            stage="failed",
            completed_at=utc_now(),
            error_message=str(exc)[:2000],
            backend_copy_ok=False if job.get("backend_copy_ok") is None else job.get("backend_copy_ok"),
            vm_copy_ok=False if job.get("vm_copy_ok") is None else job.get("vm_copy_ok"),
        )
    finally:
        if client is not None:
            client.close()


def pdb_ref_status() -> dict[str, Any]:
    path = pdb_ref_local_path()
    file_status: dict[str, Any] = {
        "available": path.is_file(),
        "name": path.name,
        "size_bytes": None,
        "modified_at": None,
    }
    if path.is_file():
        stat = path.stat()
        file_status.update(
            {
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(),
            }
        )
    job = PdbRefSyncStore().get()
    return {
        "configured": pdb_ref_sync_configured(),
        "source": "lucianavm04",
        "file": file_status,
        "job": job,
        "copies": {
            "backend": _boolean_or_none(job.get("backend_copy_ok")) if job else None,
            "vm04": _boolean_or_none(job.get("vm_copy_ok")) if job else None,
        },
    }


def pdb_ref_sync_configured() -> bool:
    if os.getenv("USE_KEYVAULT", "false").lower() == "true":
        return True
    key_path = Path(
        os.getenv(
            "PDB_REF_SSH_PRIVATE_KEY_PATH",
            os.getenv("SSH_PRIVATE_KEY_PATH", "./keys/lucianauser_key.pem"),
        )
    ).expanduser()
    return key_path.is_file()


def _connect_vm04() -> paramiko.SSHClient:
    key = _load_ssh_key()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=os.getenv("PDB_REF_VM_HOST", "20.160.158.80").strip(),
            port=int(os.getenv("PDB_REF_VM_PORT", "22")),
            username=os.getenv("PDB_REF_VM_USERNAME", "lucianauser").strip(),
            pkey=key,
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(30)
        return client
    except Exception:
        client.close()
        raise


def connect_vm04() -> paramiko.SSHClient:
    """Open the configured VM04 SSH connection for PDB data synchronization."""
    return _connect_vm04()


def _load_ssh_key() -> paramiko.PKey:
    errors = []
    if os.getenv("USE_KEYVAULT", "false").lower() == "true":
        try:
            vault_name = os.getenv("KEY_VAULT_NAME", "luciana-project")
            secret_name = os.getenv(
                "PDB_REF_SSH_PRIVATE_KEY_SECRET",
                os.getenv("CONTROL_PANEL_SSH_PRIVATE_KEY_SECRET", "ssh-private-key-lucianauser"),
            )
            credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=True
            )
            value = SecretClient(
                vault_url=f"https://{vault_name}.vault.azure.net/",
                credential=credential,
            ).get_secret(secret_name).value
            return paramiko.RSAKey.from_private_key(io.StringIO(value or ""))
        except Exception as exc:
            errors.append(f"Key Vault: {exc}")

    key_path = os.getenv(
        "PDB_REF_SSH_PRIVATE_KEY_PATH",
        os.getenv("SSH_PRIVATE_KEY_PATH", "./keys/lucianauser_key.pem"),
    )
    try:
        return paramiko.RSAKey.from_private_key_file(str(Path(key_path).expanduser()))
    except Exception as exc:
        errors.append(f"file key: {exc}")
    raise PdbRefSyncError("Chiave SSH lucianavm04 non disponibile (" + "; ".join(errors) + ")")


def _run_remote(client: paramiko.SSHClient, command: str, timeout: int) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    stdout.channel.settimeout(timeout)
    output = stdout.read().decode("utf-8", errors="replace")
    error = stderr.read().decode("utf-8", errors="replace")
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        detail = (error or output or f"exit status {exit_status}").strip()
        raise PdbRefSyncError(f"Comando lucianavm04 non riuscito: {detail[:1000]}")
    return output


def _download_parquet(
    client: paramiko.SSHClient, remote_path: str
) -> tuple[int, int]:
    target = pdb_ref_local_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    sftp = client.open_sftp()
    try:
        remote_size = int(sftp.stat(remote_path).st_size)
        if remote_size <= 8 or remote_size > MAX_PARQUET_BYTES:
            raise PdbRefSyncError("Dimensione del Reference PDB non valida")
        with sftp.file(remote_path, "rb") as source, temporary.open("wb") as destination:
            shutil.copyfileobj(source, destination, length=4 * 1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        local_size = temporary.stat().st_size
        if local_size != remote_size:
            raise PdbRefSyncError(
                f"Parquet incompleto: ricevuti {local_size} byte, attesi {remote_size}"
            )
        _validate_parquet_envelope(temporary)
        os.replace(temporary, target)
        return local_size, remote_size
    finally:
        sftp.close()
        temporary.unlink(missing_ok=True)


def _validate_parquet_envelope(path: Path) -> None:
    with path.open("rb") as stream:
        if stream.read(4) != b"PAR1":
            raise PdbRefSyncError("Header Parquet non valido")
        stream.seek(-4, os.SEEK_END)
        if stream.read(4) != b"PAR1":
            raise PdbRefSyncError("Footer Parquet non valido")


def _parse_key_values(output: str) -> dict[str, str]:
    result = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().replace("_", "").isalnum():
            result[key.strip()] = value.strip()
    return result


def _parse_json_line(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise PdbRefSyncError("Il builder BS25 non ha restituito metadati validi")


def _integer_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _boolean_or_none(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _is_stale(updated_at: str) -> bool:
    try:
        parsed = datetime.fromisoformat(updated_at)
    except (TypeError, ValueError):
        return True
    stale_after = int(os.getenv("PDB_REF_SYNC_STALE_SECONDS", "10800"))
    return parsed < datetime.now(timezone.utc) - timedelta(seconds=stale_after)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
