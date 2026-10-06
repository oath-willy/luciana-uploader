from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shlex
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

import paramiko

from services import fast_track_performance as performance
from services.pdb_ref_sync import _load_ssh_key, pdb_ref_sync_configured

FOLDERS = {"gold": "gold_monitoring_dashboard", "forecast": "forecast_dashboard"}
LABELS = {"gold": "Gold monitoring", "forecast": "Forecast"}
SCRIPT_KEYS = ("gold_links", "gold_status", "forecast_links")
REVISION = re.compile(r"^[a-f0-9]{32}$")
SOURCE_EXTENSIONS = {".html", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".woff", ".woff2", ".R"}
PUBLIC_EXTENSIONS = SOURCE_EXTENSIONS - {".R"}
MAX_SOURCE_BYTES = 32 * 1024 * 1024
# Verified against the user's existing OpenSSH known_hosts for lucianavm04, not trust on first use.
VM04_HOST_KEYS = {
    "SHA256:5D8y9kBgyOPN7GRLG30upVcVyjcum2KbDY/YrOYsNEQ",
    "SHA256:6tpZR+fvSc1XQ0TcpgPqTOGkiSThqZkTehVPJKBDBs0",
    "SHA256:VqoGjTYazN7scJFpWK7gTHcR0rdykr/167WhwjwBkzs",
}


class PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        configured = os.getenv("FAST_TRACK_SSH_HOST_KEY_SHA256", "").strip()
        allowed = {value.strip() for value in configured.split(",")} if configured else VM04_HOST_KEYS
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        if fingerprint not in allowed:
            raise paramiko.SSHException("Chiave host lucianavm04 non riconosciuta; verificare la configurazione SSH Fast Track")


def _credential_identity():
    path = Path(os.getenv("PDB_REF_SSH_PRIVATE_KEY_PATH", os.getenv("SSH_PRIVATE_KEY_PATH", "./keys/lucianauser_key.pem"))).expanduser()
    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stamp = None
    return (os.getenv("USE_KEYVAULT", "false"), os.getenv("KEY_VAULT_NAME", "luciana-project"),
            os.getenv("PDB_REF_SSH_PRIVATE_KEY_SECRET", os.getenv("CONTROL_PANEL_SSH_PRIVATE_KEY_SECRET", "ssh-private-key-lucianauser")),
            str(path.resolve()), stamp)


def _remote_identity():
    return (os.getenv("PDB_REF_VM_HOST", "20.160.158.80").strip(), int(os.getenv("PDB_REF_VM_PORT", "22")),
            os.getenv("PDB_REF_VM_USERNAME", "lucianauser").strip(),
            os.getenv("FAST_TRACK_SSH_HOST_KEY_SHA256", "").strip(), _credential_identity())


def _connect_remote():
    optimized = performance.optimizations_enabled()
    # A rejected cached credential is refreshed once, so key rotation does not wait for TTL.
    for attempt in range(2 if optimized else 1):
        key = performance.ssh_key.get(_credential_identity(), _load_ssh_key) if optimized else _load_ssh_key()
        try:
            return _connect_with_key(key)
        except paramiko.AuthenticationException:
            performance.ssh_key.clear()
            if not optimized or attempt:
                raise


def _connect_with_key(key):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(PinnedHostKeyPolicy())
    try:
        client.connect(hostname=os.getenv("PDB_REF_VM_HOST", "20.160.158.80").strip(),
                       port=int(os.getenv("PDB_REF_VM_PORT", "22")),
                       username=os.getenv("PDB_REF_VM_USERNAME", "lucianauser").strip(), pkey=key,
                       timeout=20, banner_timeout=20, auth_timeout=20, look_for_keys=False, allow_agent=False)
        client.get_transport().set_keepalive(30)
        return client
    except BaseException:
        client.close()
        raise


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enabled() -> bool:
    return os.getenv("FAST_TRACK_ENABLED", "true").lower() == "true"


def data_dir() -> Path:
    configured = os.getenv("FAST_TRACK_LOCAL_DIR", "").strip()
    cloud = bool(os.getenv("WEBSITE_SITE_NAME") or os.getenv("WEBSITE_INSTANCE_ID"))
    path = Path(configured).expanduser() if configured else (
        Path("/home/data/fast-track") if cloud else Path(__file__).resolve().parents[1] / "data/fast-track"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_config() -> dict[str, Any]:
    user = os.getenv("FAST_TRACK_SOURCE_USER", "wilson_sgroi").strip()
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,63}", user):
        raise ValueError("Utente sorgente Fast Track non valido")
    root = os.getenv("FAST_TRACK_SOURCE_ROOT", f"/home/{user}/dtl_fast-track").strip()
    if not root.startswith("/") or ".." in PurePosixPath(root).parts:
        raise ValueError("Cartella sorgente Fast Track non valida")
    return {"source_user": user, "source_root": root,
            "rscript": os.getenv("FAST_TRACK_RSCRIPT", "/opt/R/4.5.2/bin/Rscript"),
            "timeout": int(os.getenv("FAST_TRACK_JOB_TIMEOUT_SECONDS", "3600"))}


class Store:
    """Shared SQLite claim, job history and atomic pointers to successful publications."""
    @contextmanager
    def connect(self):
        db = sqlite3.connect(data_dir() / "settings.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=30000")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT, target TEXT, status TEXT, stage TEXT,
                requested_by TEXT, requested_at TEXT, updated_at TEXT, completed_at TEXT,
                error_message TEXT, results TEXT NOT NULL DEFAULT '{}')""")
            db.commit()
            yield db
        finally:
            db.close()

    def meta(self, key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def job(self, kind: str | None = None) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs " + ("WHERE kind=? " if kind else "") +
                             "ORDER BY requested_at DESC LIMIT 1", (kind,) if kind else ()).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["results"] = json.loads(result["results"])
        return result

    def claim(self, kind: str, target: str, user: str) -> str | None:
        identifier = uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=source_config()["timeout"] + 300)).isoformat()
            db.execute("""UPDATE jobs SET status='failed', stage='failed', completed_at=?,
                error_message='Aggiornamento interrotto; la versione pubblicata precedente e conservata'
                WHERE status IN ('queued','running') AND updated_at < ?""", (now(), cutoff))
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
                db.commit()
                return None
            stamp = now()
            db.execute("INSERT INTO jobs (id,kind,target,status,stage,requested_by,requested_at,updated_at) "
                       "VALUES (?,?,?,'queued','queued',?,?,?)", (identifier, kind, target, user, stamp, stamp))
            db.commit()
        return identifier

    def update(self, identifier: str, **values: Any):
        allowed = {"status", "stage", "completed_at", "error_message", "results"}
        values = {key: value for key, value in values.items() if key in allowed}
        if "results" in values:
            values["results"] = json.dumps(values["results"])
        values["updated_at"] = now()
        with self.connect() as db:
            db.execute("UPDATE jobs SET " + ",".join(key + "=?" for key in values) + " WHERE id=?",
                       (*values.values(), identifier))
            db.commit()

    def complete(self, identifier: str, metadata: dict[str, dict[str, Any]]):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # A stale/replaced job must never activate a late result.
            row = db.execute("SELECT status FROM jobs WHERE id=?", (identifier,)).fetchone()
            if row is None or row[0] not in {"queued", "running"}:
                raise RuntimeError("Aggiornamento scaduto: versione non pubblicata")
            for key, value in metadata.items():
                db.execute("INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (key, json.dumps(value)))
            stamp = now()
            db.execute("UPDATE jobs SET status='completed', stage='completed', completed_at=?, updated_at=? WHERE id=?",
                       (stamp, stamp, identifier))
            db.commit()


def status() -> dict[str, Any]:
    store = Store()
    sources = store.meta("sources") or {}
    publication = store.meta("publication") or {}
    job = store.job()
    return {
        "enabled": enabled(), "configured": pdb_ref_sync_configured(),
        "source_user": source_config()["source_user"], "source_root": source_config()["source_root"],
        "active": bool(job and job["status"] in {"queued", "running"}),
        "sources": {"updated_at": sources.get("updated_at"), "dashboards": sources.get("dashboards", {}),
                    "job": store.job("sources")},
        "data": {"updated_at": publication.get("updated_at"), "scripts": publication.get("scripts", {}),
                 "job": store.job("data")},
        "dashboards": {key: {
            "label": LABELS[key], **publication.get("dashboards", {}).get(key, {}),
            "url": f"/api/fast-track/content/{publication['revision']}/{folder}/index.html"
                   if publication.get("dashboards", {}).get(key, {}).get("available") else None,
            "pending_sources": bool(sources and (
                sources.get("dashboards", {}).get(key, {}).get("sha256") != publication.get("source_hashes", {}).get(key)
                if publication.get("source_hashes") else sources.get("revision") != publication.get("source_revision"))),
        } for key, folder in FOLDERS.items()},
    }


def _open_remote(config: dict[str, Any]):
    pooled = config["action"] == "read" and performance.optimizations_enabled()
    # Jobs use dedicated connections. Read-only commands may retry a stale pooled session.
    for attempt in range(2 if pooled else 1):
        client = performance.ssh_reads.acquire(_remote_identity(), _connect_remote) if pooled else _connect_remote()
        try:
            helper = Path(__file__).with_name("fast_track_remote.py").read_bytes()
            code = "import base64; exec(compile(base64.b64decode(" + repr(base64.b64encode(helper).decode()) + "), '<fast-track>', 'exec'))"
            command = "sudo -n -H -u " + shlex.quote(config["source_user"]) + " -- python3 -c " + shlex.quote(code)
            stdin, stdout, stderr = client.exec_command("cd /tmp && " + command, timeout=config["timeout"] + 60)
            stdin.write(json.dumps(config))
            stdin.flush()
            stdin.channel.shutdown_write()
            return client, stdout, stderr
        except (paramiko.SSHException, EOFError, OSError):
            client.close()
            if not pooled or attempt:
                raise
        except BaseException:
            client.close()
            raise


def _safe_source_path(name: str) -> PurePosixPath:
    rel = PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts or "\\" in name or not rel.parts:
        raise ValueError("Percorso sorgente non valido")
    if rel.parts[0] not in {*FOLDERS.values(), "assets"} or any(part.startswith(".") for part in rel.parts):
        raise ValueError("File sorgente non consentito")
    archive = rel.as_posix() == "gold_monitoring_dashboard/data/archive.json"
    if not archive and ("data" in rel.parts or "docs" in rel.parts or rel.suffix not in SOURCE_EXTENSIONS):
        raise ValueError("File sorgente non consentito")
    return rel


def _validate_sources(root: Path):
    if sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) > MAX_SOURCE_BYTES:
        raise ValueError("Sorgenti oltre il limite di 32 MB")
    for folder in FOLDERS.values():
        index = root / folder / "index.html"
        if not index.is_file() or not (root / folder / "support.js").is_file() or not (root / folder / "link_runs.R").is_file():
            raise ValueError("Sorgenti incompleti: " + folder)
        html = index.read_text(encoding="utf-8")
        match = re.search(r"url\s*=\s*([^\"'<>;]+)", html, re.I)
        entry = unquote(match[1].strip()) if match else ""
        if not entry.endswith(".html") or PurePosixPath(entry).name != entry or not (root / folder / entry).is_file():
            raise ValueError("Pagina iniziale non valida: " + folder)
    if not (root / FOLDERS["gold"] / "collection_status.R").is_file():
        raise ValueError("Script collection_status.R mancante")


def _source_files(revision: str) -> dict[str, str]:
    root = data_dir() / "sources" / revision
    files = {}
    for path in root.rglob("*"):
        if path.is_file():
            name = path.relative_to(root).as_posix()
            _safe_source_path(name)
            files[name] = base64.b64encode(path.read_bytes()).decode()
    return files


def run_job(identifier: str, kind: str, target: str):
    store = Store()
    store.update(identifier, status="running", stage="downloading" if kind == "sources" else "preparing")
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(20):
            store.update(identifier)
    watcher = threading.Thread(target=heartbeat, daemon=True)
    watcher.start()
    client = None
    staging = None
    try:
        config = {**source_config(), "action": kind, "target": target}
        if kind == "sources":
            old = store.meta("sources") or {}
            if target != "all" and old and old.get("source_user") != config["source_user"]:
                raise ValueError("Utente sorgente cambiato: recupera entrambe le dashboard")
            if target != "all" and not old:
                raise ValueError("Al primo aggiornamento recupera entrambe le dashboard")
            client, stdout, stderr = _open_remote(config)
            output = stdout.read(MAX_SOURCE_BYTES * 2 + 1)
            if len(output) > MAX_SOURCE_BYTES * 2:
                raise ValueError("Risposta sorgenti oltre il limite")
            if stdout.channel.recv_exit_status() != 0:
                raise RuntimeError((stderr.read().decode(errors="replace") or output.decode(errors="replace"))[-2000:])
            payload = json.loads(output)
            if "error" in payload:
                raise RuntimeError(payload["error"])
            staging = data_dir() / "sources" / identifier
            if target != "all":
                shutil.copytree(data_dir() / "sources" / old["revision"], staging)
                shutil.rmtree(staging / FOLDERS[target])
            staging.mkdir(parents=True, exist_ok=True)
            total = 0
            for name, encoded in payload["files"].items():
                rel = _safe_source_path(name)
                content = base64.b64decode(encoded, validate=True)
                total += len(content)
                if total > MAX_SOURCE_BYTES:
                    raise ValueError("Sorgenti oltre il limite")
                dest = staging.joinpath(*rel.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
            _validate_sources(staging)
            stamp = now()
            dashboards = dict(old.get("dashboards", {}))
            for key, folder in FOLDERS.items():
                # Shared assets affect both dashboards even when only one source is refreshed.
                digest = hashlib.sha256()
                for path in sorted([*(staging / folder).rglob("*"), *(staging / "assets").rglob("*")]):
                    if path.is_file():
                        digest.update(path.relative_to(staging).as_posix().encode())
                        digest.update(path.read_bytes())
                dashboards[key] = {"available": True,
                    "updated_at": stamp if target in {"all", key} else dashboards[key]["updated_at"],
                    "sha256": digest.hexdigest()}
            store.complete(identifier, {"sources": {"revision": identifier, "updated_at": stamp,
                                                    "source_user": config["source_user"], "dashboards": dashboards}})
            staging = None
        else:
            sources = store.meta("sources")
            if not sources:
                raise ValueError("Recupera prima i sorgenti delle dashboard")
            if sources["source_user"] != config["source_user"]:
                raise ValueError("Utente sorgente cambiato: recupera prima entrambe le dashboard")
            previous = store.meta("publication") or {}
            config.update(revision=identifier, files=_source_files(sources["revision"]), previous=previous)
            client, stdout, stderr = _open_remote(config)
            results = {}
            completed = None
            for line in stdout:
                event = json.loads(line)
                if "error" in event:
                    raise RuntimeError(event["error"])
                if "stage" in event:
                    store.update(identifier, stage=event["stage"])
                if "result" in event:
                    results[event["result"]] = {"completed_at": now(), "message": event.get("message", "")}
                    store.update(identifier, results=results)
                if event.get("completed"):
                    completed = event
            if stdout.channel.recv_exit_status() != 0 or completed is None:
                raise RuntimeError((stderr.read().decode(errors="replace") or "Aggiornamento dati non completato")[-2000:])
            stamp = now()
            scripts = dict(previous.get("scripts", {}))
            scripts.update(results)
            publication = {"revision": identifier, "source_revision": sources["revision"], "source_user": config["source_user"],
                           "updated_at": stamp, "dashboards": completed["dashboards"], "scripts": scripts,
                           "source_hashes": {key: value.get("sha256") for key, value in sources["dashboards"].items()},
                           "json_hashes": completed.get("json_hashes", {})}
            for key, value in publication["dashboards"].items():
                relevant = {"gold_links", "gold_status"} if key == "gold" else {"forecast_links"}
                value["updated_at"] = stamp if relevant.intersection(results) else previous.get("dashboards", {}).get(key, {}).get("updated_at")
            store.complete(identifier, {"publication": publication, "publication:" + identifier: publication})
    except Exception as error:
        store.update(identifier, status="failed", stage="failed", completed_at=now(), error_message=str(error)[:2000])
    finally:
        stop.set()
        watcher.join(timeout=2)
        if client is not None:
            client.close()
        if staging is not None:
            shutil.rmtree(staging)


def publication_file(revision: str, name: str):
    """Validate every request before using the private, versioned data cache."""
    if not REVISION.fullmatch(revision):
        raise FileNotFoundError("Versione non disponibile")
    publication = Store().meta("publication:" + revision)
    if publication is None:
        raise FileNotFoundError("Versione non disponibile")
    rel = PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts or "\\" in name or any(p.startswith(".") for p in rel.parts):
        raise FileNotFoundError("File non disponibile")
    if not rel.parts or rel.parts[0] not in {*FOLDERS.values(), "assets"}:
        raise FileNotFoundError("File non disponibile")
    if "data" not in rel.parts:
        if rel.suffix not in PUBLIC_EXTENSIONS:
            raise FileNotFoundError("File non disponibile")
        root = data_dir() / "sources" / publication["source_revision"]
        path = root.joinpath(*rel.parts)
        path.resolve().relative_to(root.resolve())
        if not path.is_file():
            raise FileNotFoundError("File non disponibile")
        mime = {".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml"}.get(path.suffix)
        return path, mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if "models" in rel.parts or rel.suffix not in {".json", ".parquet", ".xlsx"}:
        raise FileNotFoundError("File non disponibile")
    config = {**source_config(), "source_user": publication["source_user"], "action": "read", "revision": revision, "path": name,
              "timeout": int(os.getenv("FAST_TRACK_FILE_TIMEOUT_SECONDS", "180"))}
    if performance.optimizations_enabled():
        key = (str(data_dir().resolve()), _remote_identity(), publication["source_user"], revision, rel.as_posix())
        return performance.files.fetch(key, lambda: _remote_file(config, rel))
    return _remote_file(config, rel)


def _remote_file(config: dict[str, Any], rel: PurePosixPath):
    client, stdout, stderr = _open_remote(config)
    try:
        header = json.loads(stdout.readline(4096))
        if "error" in header:
            # A normal helper error (e.g. an optional table missing) does not break SSH.
            # Drain the command before returning its connection; never cache the error.
            if isinstance(client, performance.SSHLease) and not stdout.read(4096):
                stdout.channel.recv_exit_status()
                client.mark_complete()
            raise FileNotFoundError(header["error"])
        size = header["size"]
        if not isinstance(size, int) or not 0 <= size <= 512 * 1024 * 1024:
            raise ValueError("Dimensione file non valida")
    except BaseException:
        client.close()
        raise
    def chunks():
        try:
            remaining = size
            while remaining:
                block = stdout.read(min(512 * 1024, remaining))
                if not block or len(block) > remaining:
                    raise IOError("Trasferimento dati incompleto")
                remaining -= len(block)
                yield block
            if stdout.channel.recv_exit_status() != 0:
                raise IOError("Lettura dati non completata")
            if isinstance(client, performance.SSHLease):
                client.mark_complete()
        finally:
            client.close()
    mime = {".json": "application/json", ".parquet": "application/octet-stream",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[rel.suffix]
    return chunks(), mime, size, client.close
