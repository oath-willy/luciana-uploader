from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from filelock import FileLock, Timeout

from services.items_code_browse_cache import QUERY_SLOTS
from services.mc_code_local_store import SnapshotUnavailable
from services.pdb_brands_dictionary_sync import brands_dictionary_path


REQUIRED_COLUMNS = frozenset({"id", "brand", "prefix", "brand_raw"})
BRAND_FILTERS = frozenset({"brand", "prefix"})
RAW_FILTERS = frozenset({"brand_raw"})
WORKSPACE_FILE_NAME = "pdb_brands_dictionary_workspace.sqlite3"
REQUESTED_WORKSPACE_FILE_NAME = "pdb_brands_dictionary_workspace.sqllite3"
LEGACY_RUNTIME_FILE_NAME = "runtime_pdb_brands_dictionary.sqlite3"
LEGACY_EDITS_FILE_NAME = "pdb_brands_dictionary_edits.parquet"
# Schema del vecchio overlay Parquet, mantenuto soltanto per la migrazione.
EDITS_SCHEMA = pa.schema(
    [
        pa.field("record_key", pa.string(), nullable=False),
        pa.field("source_key", pa.string()),
        pa.field("brand", pa.string(), nullable=False),
        pa.field("brand_raw", pa.string(), nullable=False),
        pa.field("is_new", pa.bool_(), nullable=False),
        pa.field("updated_at", pa.string(), nullable=False),
    ]
)
WORKSPACE_SCHEMA = pa.schema(
    [
        pa.field("record_key", pa.string(), nullable=False),
        pa.field("source_id", pa.int64()),
        pa.field("brand", pa.string(), nullable=False),
        pa.field("brand_raw", pa.string(), nullable=False),
        pa.field("is_new", pa.bool_(), nullable=False),
        pa.field("updated_at", pa.string(), nullable=False),
    ]
)


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _like(value: str) -> str:
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _stamp(path: Path) -> tuple[str, int, int]:
    if not path.is_file():
        raise SnapshotUnavailable(
            f"File {path.name} assente. Recuperarlo da PDB Settings."
        )
    stat = path.stat()
    return str(path.resolve()), stat.st_mtime_ns, stat.st_size


def brands_workspace_path() -> Path:
    configured = os.getenv("PDB_BRANDS_DICTIONARY_WORKSPACE_DB", "").strip()
    if configured:
        target = Path(configured).expanduser()
    else:
        source = brands_dictionary_path()
        canonical = source.with_name(WORKSPACE_FILE_NAME)
        requested = source.with_name(REQUESTED_WORKSPACE_FILE_NAME)
        target = requested if requested.is_file() and not canonical.is_file() else canonical
    _migrate_legacy_workspace(target)
    _upgrade_workspace(target)
    return target


def brands_runtime_path() -> Path:
    """Compatibility alias for callers introduced with the first SQLite overlay."""
    return brands_workspace_path()


def _legacy_edits_path() -> Path:
    configured = os.getenv("PDB_BRANDS_DICTIONARY_EDITS_PATH", "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else brands_dictionary_path().with_name(LEGACY_EDITS_FILE_NAME)
    )


def _legacy_runtime_paths() -> list[Path]:
    configured = os.getenv("PDB_BRANDS_DICTIONARY_RUNTIME_DB", "").strip()
    paths = []
    if configured:
        paths.append(Path(configured).expanduser())
    paths.append(brands_dictionary_path().with_name(LEGACY_RUNTIME_FILE_NAME))
    return list(dict.fromkeys(paths))


def _source_id_from_legacy_key(value: str | None) -> int | None:
    if not value:
        return None
    if value.startswith("id:"):
        try:
            return int(value[3:])
        except ValueError as exc:
            raise ValueError(f"Riferimento legacy non valido: {value}") from exc
    if value.startswith("row:"):
        try:
            row_number = int(value[4:])
        except ValueError as exc:
            raise ValueError(f"Riferimento legacy non valido: {value}") from exc
        source_path = brands_dictionary_path()
        _schema(_stamp(source_path))
        with _connection() as connection:
            row = connection.execute(
                f"SELECT TRY_CAST(id AS BIGINT) FROM "
                f"read_parquet({_literal(str(source_path))}, file_row_number=true) "
                "WHERE file_row_number = ?",
                [row_number],
            ).fetchone()
        if row is None or row[0] is None:
            raise ValueError(f"Impossibile migrare il riferimento legacy {value}")
        return int(row[0])
    raise ValueError(f"Riferimento legacy non valido: {value}")


def _convert_legacy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted = []
    for row in rows:
        is_new = bool(row["is_new"])
        source_id = row.get("source_id")
        if source_id is None and not is_new:
            source_id = _source_id_from_legacy_key(
                row.get("source_key") or row.get("record_key")
            )
        if not is_new and source_id is None:
            raise ValueError("Una modifica legacy non contiene un riferimento sorgente")
        source_id = None if source_id is None else int(source_id)
        converted.append(
            {
                "record_key": (
                    row["record_key"] if is_new else f"id:{source_id}"
                ),
                "source_id": source_id,
                "brand": row["brand"],
                "brand_raw": row["brand_raw"],
                "is_new": is_new,
                "updated_at": row["updated_at"],
            }
        )
    return converted


def _legacy_rows() -> list[dict[str, Any]] | None:
    for legacy in _legacy_runtime_paths():
        if not legacy.is_file():
            continue
        with closing(sqlite3.connect(legacy)) as connection:
            connection.row_factory = sqlite3.Row
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(brand_edits)")
            }
            if not columns:
                continue
            projection = (
                "record_key, source_id, brand, brand_raw, is_new, updated_at"
                if "source_id" in columns
                else "record_key, source_key, brand, brand_raw, is_new, updated_at"
            )
            return [dict(row) for row in connection.execute(
                f"SELECT {projection} FROM brand_edits ORDER BY record_key"
            )]
    legacy = _legacy_edits_path()
    if legacy.is_file():
        table = pq.read_table(legacy)
        if table.schema != EDITS_SCHEMA:
            raise ValueError(f"Schema non valido per {legacy.name}")
        return table.to_pylist()
    return None


def _migrate_legacy_workspace(target: Path) -> None:
    if target.is_file():
        return
    with FileLock(str(target) + ".migration.lock", timeout=30):
        if target.is_file():
            return
        legacy_rows = _legacy_rows()
        if legacy_rows is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}-migration-",
            suffix=".sqlite3",
            dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            _write_edits(temporary, _convert_legacy_rows(legacy_rows))
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def _upgrade_workspace(path: Path) -> None:
    if not path.is_file():
        return
    with closing(sqlite3.connect(path, timeout=30)) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(brand_edits)")
        }
        if not columns or "source_id" in columns:
            return
        if "source_key" not in columns:
            raise ValueError(f"Schema non valido per {path.name}")
        connection.execute("ALTER TABLE brand_edits ADD COLUMN source_id INTEGER")
        rows = connection.execute(
            "SELECT record_key, source_key, is_new FROM brand_edits"
        ).fetchall()
        for record_key, source_key, is_new in rows:
            source_id = None if is_new else _source_id_from_legacy_key(
                source_key or record_key
            )
            connection.execute(
                "UPDATE brand_edits SET source_id = ? WHERE record_key = ?",
                [source_id, record_key],
            )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_brand_edits_source_id "
            "ON brand_edits(source_id) WHERE source_id IS NOT NULL"
        )
        connection.commit()


def _empty_edits() -> pa.Table:
    return pa.Table.from_pylist([], schema=WORKSPACE_SCHEMA)


def _read_edits(path: Path | None = None) -> pa.Table:
    path = path or brands_workspace_path()
    if not path.is_file():
        return _empty_edits()
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        _initialize_runtime(connection)
        rows = [
            {
                "record_key": row["record_key"],
                "source_id": row["source_id"],
                "brand": row["brand"],
                "brand_raw": row["brand_raw"],
                "is_new": bool(row["is_new"]),
                "updated_at": row["updated_at"],
            }
            for row in connection.execute(
                "SELECT record_key, source_id, brand, brand_raw, is_new, updated_at "
                "FROM brand_edits ORDER BY record_key"
            )
        ]
    return pa.Table.from_pylist(rows, schema=WORKSPACE_SCHEMA)


def _initialize_runtime(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS brand_edits (
            record_key TEXT PRIMARY KEY,
            source_id INTEGER UNIQUE,
            brand TEXT NOT NULL,
            brand_raw TEXT NOT NULL,
            is_new INTEGER NOT NULL CHECK(is_new IN (0, 1)),
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_brand_edits_source_id "
        "ON brand_edits(source_id) WHERE source_id IS NOT NULL"
    )


def _write_edits(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda row: row["record_key"])
    with closing(sqlite3.connect(path, timeout=30)) as connection:
        _initialize_runtime(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM brand_edits")
        connection.executemany(
            """
            INSERT INTO brand_edits (
                record_key, source_id, brand, brand_raw, is_new, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["record_key"],
                    row.get("source_id"),
                    row["brand"],
                    row["brand_raw"],
                    int(bool(row["is_new"])),
                    row["updated_at"],
                )
                for row in rows
            ],
        )
        connection.commit()


@contextmanager
def _connection():
    with QUERY_SLOTS, duckdb.connect(
        config={"threads": 2, "memory_limit": "128MB"}
    ) as connection:
        connection.execute("SET enable_progress_bar = false")
        yield connection


@lru_cache(maxsize=8)
def _schema(stamp: tuple[str, int, int]) -> frozenset[str]:
    path = Path(stamp[0])
    with _connection() as connection:
        rows = connection.execute(
            f"DESCRIBE SELECT * FROM read_parquet({_literal(str(path))})"
        ).fetchall()
    columns = frozenset(row[0] for row in rows)
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(
            "Il Brands Dictionary non contiene le colonne richieste: "
            + ", ".join(sorted(missing))
        )
    with _connection() as connection:
        total, valid_ids, unique_ids = connection.execute(
            "SELECT COUNT(*), COUNT(TRY_CAST(id AS BIGINT)), "
            "COUNT(DISTINCT TRY_CAST(id AS BIGINT)) "
            f"FROM read_parquet({_literal(str(path))})"
        ).fetchone()
    if valid_ids != total:
        raise ValueError("La colonna id deve contenere solo interi non nulli")
    if unique_ids != total:
        raise ValueError("La colonna id del Brands Dictionary deve essere univoca")
    return columns


def _validate_page(page: int, page_size: int) -> None:
    if page < 0:
        raise ValueError("page non puo essere negativa")
    if page_size not in {25, 50, 100, 500}:
        raise ValueError("page_size deve essere uno tra 25, 50, 100, 500")


def _filters(
    search: str,
    filters: dict[str, str],
    allowed: frozenset[str],
) -> tuple[str, list[Any]]:
    unknown = set(filters) - allowed
    if unknown:
        raise ValueError(f"Filtro non supportato: {sorted(unknown)[0]}")

    conditions: list[str] = []
    parameters: list[Any] = []
    search = search.strip()
    if search:
        conditions.append(
            "(" + " OR ".join(
                f"COALESCE(CAST({_identifier(field)} AS VARCHAR), '') ILIKE ? ESCAPE '\\'"
                for field in sorted(allowed)
            ) + ")"
        )
        parameters.extend(_like(search) for _ in allowed)

    for field, raw_value in filters.items():
        value = str(raw_value).strip()
        if not value:
            continue
        conditions.append(
            f"COALESCE(CAST({_identifier(field)} AS VARCHAR), '') ILIKE ? ESCAPE '\\'"
        )
        parameters.append(_like(value))

    return (" WHERE " + " AND ".join(conditions) if conditions else ""), parameters


def _read_rows(connection, sql: str, parameters: list[Any]) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, parameters)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def search_brands(
    page: int,
    page_size: int,
    search: str,
    filters: dict[str, str],
) -> dict[str, Any]:
    _validate_page(page, page_size)
    path = brands_dictionary_path()
    stamp = _stamp(path)
    _schema(stamp)
    where, parameters = _filters(search, filters, BRAND_FILTERS)
    source = f"read_parquet({_literal(str(path))})"
    base = f"""
        WITH normalized AS (
            SELECT
                TRIM(CAST(brand AS VARCHAR)) AS brand,
                NULLIF(TRIM(CAST(prefix AS VARCHAR)), '') AS prefix
            FROM {source}
            WHERE brand IS NOT NULL
                AND TRIM(CAST(brand AS VARCHAR)) <> ''
        ), brands AS (
            SELECT
                brand,
                COALESCE(
                    string_agg(DISTINCT prefix, ', ' ORDER BY prefix),
                    ''
                ) AS prefix
            FROM normalized
            GROUP BY brand
        )
    """
    with _connection() as connection:
        total = connection.execute(
            base + "SELECT COUNT(*) FROM brands" + where,
            parameters,
        ).fetchone()[0]
        rows = _read_rows(
            connection,
            base
            + "SELECT brand, prefix FROM brands"
            + where
            + " ORDER BY lower(brand), brand "
            + "LIMIT ? OFFSET ?",
            [*parameters, page_size, page * page_size],
        )
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


def _source_query(path: Path) -> tuple[str, str, str]:
    source = f"read_parquet({_literal(str(path))})"
    source_id = "CAST(id AS BIGINT)"
    record_key = f"concat('id:', CAST({source_id} AS VARCHAR))"
    return source, source_id, record_key


def search_brand_raw(
    brand: str,
    page: int,
    page_size: int,
    search: str,
    filters: dict[str, str],
) -> dict[str, Any]:
    _validate_page(page, page_size)
    brand = brand.strip()
    if not brand:
        raise ValueError("brand obbligatorio")
    path = brands_dictionary_path()
    stamp = _stamp(path)
    _schema(stamp)
    filter_where, filter_parameters = _filters(search, filters, RAW_FILTERS)
    source, source_id, record_key = _source_query(path)
    base = f"""
        WITH source_occurrences AS (
            SELECT
                {record_key} AS record_key,
                {source_id} AS source_id,
                TRIM(CAST(brand_raw AS VARCHAR)) AS brand_raw
            FROM {source}
            WHERE TRIM(CAST(brand AS VARCHAR)) = ?
                AND brand_raw IS NOT NULL
                AND TRIM(CAST(brand_raw AS VARCHAR)) <> ''
        ), occurrences AS (
            SELECT
                source_occurrences.record_key,
                source_occurrences.source_id,
                COALESCE(brand_edits.brand_raw, source_occurrences.brand_raw) AS brand_raw,
                CASE
                    WHEN brand_edits.source_id IS NULL THEN 'original'
                    ELSE 'modified'
                END AS change_status
            FROM source_occurrences
            LEFT JOIN brand_edits
                ON brand_edits.source_id = source_occurrences.source_id
                AND brand_edits.is_new = FALSE

            UNION ALL

            SELECT
                record_key,
                source_id,
                brand_raw,
                'added' AS change_status
            FROM brand_edits
            WHERE is_new = TRUE
                AND brand = ?
        )
    """
    parameters = [brand, brand, *filter_parameters]
    with _connection() as connection:
        connection.register("brand_edits", _read_edits())
        total = connection.execute(
            base + "SELECT COUNT(*) FROM occurrences" + filter_where,
            parameters,
        ).fetchone()[0]
        rows = _read_rows(
            connection,
            base
            + "SELECT record_key, source_id, brand_raw, change_status FROM occurrences"
            + filter_where
            + " ORDER BY lower(brand_raw), brand_raw, record_key "
            + "LIMIT ? OFFSET ?",
            [*parameters, page_size, page * page_size],
        )
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


def _normalize_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} obbligatorio")
    if len(normalized) > 1000:
        raise ValueError(f"{field} troppo lungo")
    return normalized


def _source_brand_exists(
    connection: duckdb.DuckDBPyConnection,
    source: str,
    brand: str,
) -> bool:
    return connection.execute(
        f"SELECT 1 FROM {source} WHERE TRIM(CAST(brand AS VARCHAR)) = ? LIMIT 1",
        [brand],
    ).fetchone() is not None


def _source_record_exists(
    connection: duckdb.DuckDBPyConnection,
    source: str,
    source_id: int,
    brand: str,
) -> bool:
    return connection.execute(
        f"SELECT 1 FROM {source} "
        "WHERE CAST(id AS BIGINT) = ? "
        "AND TRIM(CAST(brand AS VARCHAR)) = ? LIMIT 1",
        [source_id, brand],
    ).fetchone() is not None


def _source_id_from_record_key(record_key: str) -> int:
    if not record_key.startswith("id:"):
        raise ValueError("Il record sorgente deve essere identificato tramite id")
    try:
        return int(record_key[3:])
    except ValueError as exc:
        raise ValueError("id del record sorgente non valido") from exc


def _saved_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_key": row["record_key"],
        "source_id": row.get("source_id"),
        "brand_raw": row["brand_raw"],
        "change_status": "added" if row["is_new"] else "modified",
    }


def update_brand_raw(record_key: str, brand: str, brand_raw: str) -> dict[str, Any]:
    record_key = _normalize_text(record_key, "record_key")
    brand = _normalize_text(brand, "brand")
    brand_raw = _normalize_text(brand_raw, "brand_raw")
    source_path = brands_dictionary_path()
    _schema(_stamp(source_path))
    source, _, _ = _source_query(source_path)
    edits_path = brands_workspace_path()
    is_added_record = record_key.startswith("new:")
    source_id = None if is_added_record else _source_id_from_record_key(record_key)
    canonical_record_key = record_key if is_added_record else f"id:{source_id}"

    try:
        with FileLock(str(edits_path) + ".lock", timeout=30):
            rows = _read_edits(edits_path).to_pylist()
            existing = next(
                (
                    row
                    for row in rows
                    if (
                        row["record_key"] == canonical_record_key
                        if is_added_record
                        else row.get("source_id") == source_id
                    )
                ),
                None,
            )
            if existing is not None:
                if existing["is_new"]:
                    if existing["brand"] != brand:
                        raise ValueError("Il record non appartiene al brand selezionato")
                else:
                    with _connection() as connection:
                        if not _source_record_exists(
                            connection,
                            source,
                            source_id,
                            brand,
                        ):
                            raise ValueError("Occorrenza brand_raw non trovata")
                    existing["brand"] = brand
                existing["brand_raw"] = brand_raw
                existing["updated_at"] = datetime.now(timezone.utc).isoformat()
                if not existing["is_new"]:
                    existing["record_key"] = canonical_record_key
                saved = existing
            else:
                if is_added_record:
                    raise ValueError("Occorrenza brand_raw aggiunta non trovata")
                with _connection() as connection:
                    if not _source_record_exists(
                        connection,
                        source,
                        source_id,
                        brand,
                    ):
                        raise ValueError("Occorrenza brand_raw non trovata")
                saved = {
                    "record_key": canonical_record_key,
                    "source_id": source_id,
                    "brand": brand,
                    "brand_raw": brand_raw,
                    "is_new": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                rows.append(saved)
            _write_edits(edits_path, rows)
    except Timeout as exc:
        raise ValueError("Archivio modifiche occupato; riprovare") from exc

    return {
        "row": _saved_row(saved),
        "workspace_file": edits_path.name,
        "runtime_file": edits_path.name,
        "edits_file": edits_path.name,
    }


def create_brand_raw(brand: str, brand_raw: str) -> dict[str, Any]:
    brand = _normalize_text(brand, "brand")
    brand_raw = _normalize_text(brand_raw, "brand_raw")
    source_path = brands_dictionary_path()
    _schema(_stamp(source_path))
    source, _, _ = _source_query(source_path)
    edits_path = brands_workspace_path()

    try:
        with FileLock(str(edits_path) + ".lock", timeout=30):
            with _connection() as connection:
                if not _source_brand_exists(connection, source, brand):
                    raise ValueError("Brand non trovato nel Brands Dictionary")
            rows = _read_edits(edits_path).to_pylist()
            saved = {
                "record_key": f"new:{uuid4().hex}",
                "source_id": None,
                "brand": brand,
                "brand_raw": brand_raw,
                "is_new": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(saved)
            _write_edits(edits_path, rows)
    except Timeout as exc:
        raise ValueError("Archivio modifiche occupato; riprovare") from exc

    return {
        "row": _saved_row(saved),
        "workspace_file": edits_path.name,
        "runtime_file": edits_path.name,
        "edits_file": edits_path.name,
    }
