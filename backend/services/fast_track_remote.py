"""Self-contained VM helper. Runs as the configured source user, outside RStudio."""
import base64
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

FOLDERS = {"gold": "gold_monitoring_dashboard", "forecast": "forecast_dashboard"}
SCRIPTS = {
    "gold_links": "dashboard/gold_monitoring_dashboard/link_runs.R",
    "gold_status": "dashboard/gold_monitoring_dashboard/collection_status.R",
    "forecast_links": "dashboard/forecast_dashboard/link_runs.R",
}
EXTENSIONS = {".html", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".woff", ".woff2", ".R"}
DATA_ROOTS = ("/mnt/gold/reports/fast_track", "/mnt/consumption/fast_track/forecast")
MAX_SOURCE_BYTES = 32 * 1024 * 1024


def emit(value):
    print(json.dumps(value), flush=True)


def release_root():
    # sudo -H sets HOME to the source user. This also keeps the helper importable in Windows tests.
    return pathlib.Path.home() / ".local/share/luciana-fast-track-webapp/releases"


def release_path(revision):
    if len(revision) != 32 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Versione non valida")
    return release_root() / revision


def export_sources(config):
    root = pathlib.Path(config["source_root"]) / "dashboard"
    selected = [FOLDERS[config["target"]]] if config["target"] != "all" else list(FOLDERS.values())
    files, total = {}, 0
    for folder in ["assets", *selected]:
        for path in sorted((root / folder).rglob("*")):
            rel = path.relative_to(root)
            if "data" in rel.parts or "docs" in rel.parts or any(p.startswith(".") for p in rel.parts):
                continue
            if path.is_symlink() or not path.is_file() or path.suffix not in EXTENSIONS:
                continue
            path.resolve().relative_to(root.resolve())
            content = path.read_bytes()
            total += len(content)
            if total > MAX_SOURCE_BYTES:
                raise ValueError("Sorgenti dashboard oltre il limite di 32 MB")
            files[rel.as_posix()] = base64.b64encode(content).decode()
    archive = root / FOLDERS["gold"] / "data/archive.json"
    if FOLDERS["gold"] in selected and archive.is_file():
        archive.resolve().relative_to(root.resolve())
        files[archive.relative_to(root).as_posix()] = base64.b64encode(archive.read_bytes()).decode()
    emit({"files": files})


def validate_data(root, previous, rscript):
    result = {}
    gold = root / "dashboard" / FOLDERS["gold"] / "data"
    if (gold / "clients.json").is_file():
        clients = json.loads((gold / "clients.json").read_text())["clients"]
        if not clients:
            raise ValueError("Nessun cliente con una run monitoring completa")
        for client in clients:
            expected = "data/" + client["id"]
            if client.get("path") != expected or "/" in client["id"] or client["id"].startswith("."):
                raise ValueError("Percorso cliente non valido")
            link = gold / client["id"]
            if not link.is_symlink():
                raise ValueError("I dati monitoring devono essere collegamenti al blob")
            link.resolve(strict=True).relative_to(pathlib.Path(DATA_ROOTS[0]))
            if not (link / "run_manifest.parquet").is_file():
                raise ValueError("Run monitoring incompleta: " + client["id"])
        # Check the contract against the candidate scripts even when running only collection_status.
        script = (root / "dashboard" / FOLDERS["gold"] / "link_runs.R").read_text()
        version = re.search(r"dashboard_contract\s*<-\s*(\d+)L?", script)
        if not version:
            raise ValueError("Versione del contratto monitoring non dichiarata")
        validation = '''d <- "dashboard/gold_monitoring_dashboard/data";
          cl <- jsonlite::read_json(file.path(d, "clients.json"))$clients;
          for (c in cl) {
            p <- file.path(d, c$id); m <- arrow::read_parquet(file.path(p, "run_manifest.parquet"));
            stopifnot(m$contract_version[1] == VERSION);
            stopifnot(all(file.exists(file.path(p, paste0(m$table, ".parquet")))))
          }'''.replace("VERSION", version[1])
        env = dict(os.environ)
        env.pop("R_HOME", None)
        checked = subprocess.run([rscript,
                                  "--vanilla", "-e", validation], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=120)
        if checked.returncode:
            raise ValueError("Contratto o tabelle monitoring non compatibili: " + checked.stderr[-1000:])
        result["gold"] = {"available": True, "clients": len(clients), "collection_status": (gold / "collection_status.json").is_file()}
    elif previous.get("gold", {}).get("available"):
        raise ValueError("Dati monitoring precedenti non disponibili")
    forecast = root / "dashboard" / FOLDERS["forecast"] / "data"
    if (forecast / "run.json").is_file():
        run = json.loads((forecast / "run.json").read_text())
        name = run["file"]
        if pathlib.PurePosixPath(name).name != name or not name.endswith(".xlsx"):
            raise ValueError("Nome del workbook non valido")
        workbook = forecast / name
        workbook.resolve(strict=True).relative_to(pathlib.Path(DATA_ROOTS[1]))
        if not workbook.is_symlink() or workbook.stat().st_size < 8:
            raise ValueError("Workbook forecast mancante o incompleto")
        result["forecast"] = {"available": True, "run": run["run"], "size_bytes": workbook.stat().st_size}
    elif previous.get("forecast", {}).get("available"):
        raise ValueError("Dati forecast precedenti non disponibili")
    return result


def update_data(config):
    root = release_path(config["revision"])
    if root.exists():
        raise ValueError("La versione di pubblicazione esiste gia")
    root.mkdir(parents=True, mode=0o700)
    try:
        total = 0
        for name, encoded in config["files"].items():
            rel = pathlib.PurePosixPath(name)
            if rel.is_absolute() or ".." in rel.parts or "\\" in name:
                raise ValueError("Percorso sorgente non valido")
            content = base64.b64decode(encoded, validate=True)
            total += len(content)
            if total > MAX_SOURCE_BYTES:
                raise ValueError("Sorgenti troppo grandi")
            dest = root / "dashboard" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        previous = config.get("previous") or {}
        if previous.get("source_user") == config["source_user"]:
            prev_root = release_path(previous["revision"])
            for folder in FOLDERS.values():
                prev = prev_root / "dashboard" / folder / "data"
                dest = root / "dashboard" / folder / "data"
                if prev.is_dir():
                    shutil.copytree(prev, dest, symlinks=True, dirs_exist_ok=True)
        # The curated archive is part of the source update; do not overwrite it with old labels.
        archive_name = FOLDERS["gold"] + "/data/archive.json"
        if archive_name in config["files"]:
            (root / "dashboard" / archive_name).write_bytes(base64.b64decode(config["files"][archive_name], validate=True))
        # Both directories exist even on the first run; all writes stay in this isolated release.
        for folder in FOLDERS.values():
            (root / "dashboard" / folder / "data").mkdir(parents=True, exist_ok=True)
        scripts = list(SCRIPTS) if config["target"] == "all" else [config["target"]]
        deadline = time.monotonic() + config["timeout"]
        for key in scripts:
            emit({"stage": key})
            env = dict(os.environ)
            env.pop("R_HOME", None)
            outcome = subprocess.run([config["rscript"], "--vanilla", SCRIPTS[key]], cwd=root,
                                     env=env, capture_output=True, text=True,
                                     timeout=max(1, deadline - time.monotonic()))
            if outcome.returncode:
                raise RuntimeError((outcome.stderr or outcome.stdout or "Script R non riuscito")[-2000:])
            emit({"result": key, "message": (outcome.stderr or outcome.stdout)[-1000:]})
        emit({"stage": "validating"})
        dashboards = validate_data(root, previous.get("dashboards", {}), config["rscript"])
        # Hash only browser data, never model files. An immutable release keeps parallel views consistent.
        files = {}
        for folder in FOLDERS.values():
            data = root / "dashboard" / folder / "data"
            for path in data.rglob("*"):
                if path.is_file() and path.suffix == ".json" and not path.name.startswith("."):
                    files[path.relative_to(root / "dashboard").as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        emit({"completed": True, "dashboards": dashboards, "json_hashes": files})
    except BaseException:
        # rmtree does not follow the dataset symlinks. Never alter /mnt or the source repository.
        shutil.rmtree(root)
        raise


def read_data(config):
    root = release_path(config["revision"]) / "dashboard"
    rel = pathlib.PurePosixPath(config["path"])
    if rel.is_absolute() or ".." in rel.parts or "\\" in str(rel):
        raise ValueError("Percorso non valido")
    if len(rel.parts) < 3 or rel.parts[0] not in FOLDERS.values() or rel.parts[1] != "data":
        raise ValueError("File non pubblicabile")
    if "models" in rel.parts or any(p.startswith(".") for p in rel.parts):
        raise ValueError("File non pubblicabile")
    path = root.joinpath(*rel.parts)
    if path.suffix not in {".json", ".parquet", ".xlsx"} or not path.is_file():
        raise FileNotFoundError("File dashboard non disponibile")
    resolved = path.resolve(strict=True)
    allowed = [root.resolve(), *(pathlib.Path(p) for p in DATA_ROOTS)]
    if not any(resolved.is_relative_to(p) for p in allowed):
        raise ValueError("Il collegamento esce dalle sorgenti autorizzate")
    with path.open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        emit({"size": size})
        shutil.copyfileobj(stream, sys.stdout.buffer, length=512 * 1024)
        sys.stdout.buffer.flush()


def main():
    config = json.load(sys.stdin)
    try:
        {"sources": export_sources, "data": update_data, "read": read_data}[config["action"]](config)
    except Exception as error:
        emit({"error": str(error)[:2000]})
        raise SystemExit(1)


if __name__ == "__main__":
    main()
