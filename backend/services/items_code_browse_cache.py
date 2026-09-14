from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import threading
import time
from array import array
from collections import OrderedDict
from concurrent.futures import Future
from pathlib import Path
from typing import Callable

import duckdb
from filelock import FileLock, Timeout


ROW_ID = "__items_code_row_id"
COMPANY = "__items_code_company"
SEARCH_TEXT = "__items_code_search_text"
CACHE_VERSION = 1
MATCH_CACHE_BYTES = 64 * 1024 * 1024
# Two bounded query slots per worker keep four simultaneous users from spawning
# unbounded DuckDB engines. Snapshot preparation shares the same budget.
QUERY_SLOTS = threading.BoundedSemaphore(2)
logger = logging.getLogger(__name__)


def source_stamp(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return str(path.resolve()), stat.st_mtime_ns, stat.st_size


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def snapshot_path(source: Path, stamp: tuple[str, int, int]) -> Path:
    directory = Path(os.getenv("ITEMS_CODE_BROWSE_CACHE_DIR", "").strip() or source.parent / ".items-code-cache")
    digest = hashlib.sha256(repr((CACHE_VERSION, stamp)).encode()).hexdigest()[:24]
    return directory / f"pdb-{digest}.parquet"


def prepare_snapshot(source: Path, expressions: dict[str, str], company: str) -> Path:
    stamp = source_stamp(source)
    target = snapshot_path(source, stamp)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_name = hashlib.sha256(stamp[0].encode()).hexdigest()[:16]
    with FileLock(str(target.parent / f"build-{lock_name}.lock"), timeout=240):
        if target.is_file():
            return target
        descriptor, name = tempfile.mkstemp(prefix=".building-", suffix=".tmp", dir=target.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            projection = ", ".join(f"{expression} AS {_identifier(field)}" for field, expression in expressions.items())
            text_values = ", ".join(f"CAST({_identifier(field)} AS VARCHAR)" for field in expressions)
            # NUL prevents a substring from matching across two column boundaries.
            sql = (
                f"COPY (SELECT *, concat_ws(chr(0), {text_values}) AS {_identifier(SEARCH_TEXT)} "
                f"FROM (SELECT file_row_number AS {_identifier(ROW_ID)}, {company} AS {_identifier(COMPANY)}, {projection} "
                f"FROM read_parquet({_literal(str(source))}, file_row_number=true))) "
                f"TO {_literal(str(temporary))} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 16384)"
            )
            with QUERY_SLOTS, duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as connection:
                connection.execute("SET enable_progress_bar = false")
                connection.execute(sql)
            if source_stamp(source) != stamp:
                raise RuntimeError("Reference PDB changed while preparing the browsing snapshot")
            os.replace(temporary, target)
            _cleanup_old_snapshots(target)
            return target
        finally:
            temporary.unlink(missing_ok=True)


def _cleanup_old_snapshots(target: Path) -> None:
    try:
        snapshots = sorted(target.parent.glob("pdb-*.parquet"), key=lambda path: path.stat().st_mtime, reverse=True)
        for old in snapshots[2:]:
            if old != target and old.stat().st_mtime < time.time() - 86400:
                old.unlink()
    except OSError:
        logger.debug("Could not clean up an old browsing snapshot", exc_info=True)


_build_lock = threading.Lock()
_building: set[Path] = set()
_failed: dict[Path, float] = {}


def ready_snapshot(source: Path, expressions: dict[str, str], company: str) -> Path | None:
    if os.getenv("ITEMS_CODE_BROWSE_CACHE_ENABLED", "true").lower() == "false":
        return None
    target = snapshot_path(source, source_stamp(source))
    if target.is_file():
        return target
    with _build_lock:
        if target in _building or time.monotonic() - _failed.get(target, -60) < 60:
            return None
        _building.add(target)

    def build() -> None:
        try:
            prepare_snapshot(source, expressions, company)
        except (OSError, RuntimeError, duckdb.Error, Timeout):
            logger.exception("Could not prepare the PDB browsing snapshot; using the original Parquet")
            with _build_lock:
                _failed[target] = time.monotonic()
        finally:
            with _build_lock:
                _building.discard(target)

    threading.Thread(target=build, name="pdb-browse-prepare", daemon=True).start()
    return None


class MatchCache:
    """Bounded, per-process LRU of row identifiers, never complete product rows."""

    def __init__(self, max_bytes: int = MATCH_CACHE_BYTES, max_entries: int = 32):
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._bytes = 0
        self._entries: OrderedDict[tuple, tuple[int, array | None]] = OrderedDict()
        self._pending: dict[tuple, Future] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple, loader: Callable[[], tuple[int, array | None]]) -> tuple[int, array | None]:
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]
            pending = self._pending.get(key)
            owner = pending is None
            if owner:
                pending = Future()
                self._pending[key] = pending
        if not owner:
            return pending.result()
        try:
            result = loader()
            size = len(result[1]) * result[1].itemsize if result[1] is not None else 0
            with self._lock:
                if size <= self.max_bytes:
                    while self._entries and (self._bytes + size > self.max_bytes or len(self._entries) >= self.max_entries):
                        _, evicted = self._entries.popitem(last=False)
                        self._bytes -= len(evicted[1]) * evicted[1].itemsize if evicted[1] is not None else 0
                    self._entries[key] = result
                    self._bytes += size
            pending.set_result(result)
            return result
        except BaseException as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)


matches = MatchCache()
