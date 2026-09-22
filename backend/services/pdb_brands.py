from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
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


REQUIRED_COLUMNS = frozenset({"brand", "prefix", "brand_raw"})
BRAND_FILTERS = frozenset({"brand", "prefix"})
RAW_FILTERS = frozenset({"brand_raw"})
EDITS_FILE_NAME = "pdb_brands_dictionary_edits.parquet"
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


def brands_edits_path() -> Path:
    configured = os.getenv("PDB_BRANDS_DICTIONARY_EDITS_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return brands_dictionary_path().with_name(EDITS_FILE_NAME)


def _empty_edits() -> pa.Table:
    return pa.Table.from_pylist([], schema=EDITS_SCHEMA)


def _read_edits(path: Path | None = None) -> pa.Table:
    path = path or brands_edits_path()
    if not path.is_file():
        return _empty_edits()
    table = pq.read_table(path)
    if table.schema != EDITS_SCHEMA:
        raise ValueError(f"Schema non valido per {path.name}")
    return table


def _write_edits(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda row: row["record_key"])
    table = pa.Table.from_pylist(rows, schema=EDITS_SCHEMA)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-", suffix=".parquet", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        pq.write_table(table, temporary, compression="zstd")
        with temporary.open("r+b") as written:
            written.flush()
            os.fsync(written.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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


def _source_query(path: Path, columns: frozenset[str]) -> tuple[str, str]:
    source = f"read_parquet({_literal(str(path))}, file_row_number=true)"
    if "id" in columns:
        record_key = (
            "CASE WHEN id IS NULL "
            "THEN concat('row:', CAST(file_row_number AS VARCHAR)) "
            "ELSE concat('id:', CAST(id AS VARCHAR)) END"
        )
    else:
        record_key = "concat('row:', CAST(file_row_number AS VARCHAR))"
    return source, record_key


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
    columns = _schema(stamp)
    filter_where, filter_parameters = _filters(search, filters, RAW_FILTERS)
    source, record_key = _source_query(path, columns)
    base = f"""
        WITH source_occurrences AS (
            SELECT
                {record_key} AS record_key,
                TRIM(CAST(brand_raw AS VARCHAR)) AS brand_raw
            FROM {source}
            WHERE TRIM(CAST(brand AS VARCHAR)) = ?
                AND brand_raw IS NOT NULL
                AND TRIM(CAST(brand_raw AS VARCHAR)) <> ''
        ), occurrences AS (
            SELECT
                source_occurrences.record_key,
                COALESCE(brand_edits.brand_raw, source_occurrences.brand_raw) AS brand_raw,
                CASE
                    WHEN brand_edits.record_key IS NULL THEN 'original'
                    ELSE 'modified'
                END AS change_status
            FROM source_occurrences
            LEFT JOIN brand_edits
                ON brand_edits.record_key = source_occurrences.record_key
                AND brand_edits.is_new = FALSE

            UNION ALL

            SELECT
                record_key,
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
            + "SELECT record_key, brand_raw, change_status FROM occurrences"
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
    record_key_expression: str,
    record_key: str,
    brand: str,
) -> bool:
    return connection.execute(
        f"SELECT 1 FROM {source} "
        f"WHERE {record_key_expression} = ? "
        "AND TRIM(CAST(brand AS VARCHAR)) = ? LIMIT 1",
        [record_key, brand],
    ).fetchone() is not None


def _saved_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_key": row["record_key"],
        "brand_raw": row["brand_raw"],
        "change_status": "added" if row["is_new"] else "modified",
    }


def update_brand_raw(record_key: str, brand: str, brand_raw: str) -> dict[str, Any]:
    record_key = _normalize_text(record_key, "record_key")
    brand = _normalize_text(brand, "brand")
    brand_raw = _normalize_text(brand_raw, "brand_raw")
    source_path = brands_dictionary_path()
    columns = _schema(_stamp(source_path))
    source, record_key_expression = _source_query(source_path, columns)
    edits_path = brands_edits_path()

    try:
        with FileLock(str(edits_path) + ".lock", timeout=30):
            rows = _read_edits(edits_path).to_pylist()
            existing = next(
                (row for row in rows if row["record_key"] == record_key),
                None,
            )
            if existing is not None:
                if existing["brand"] != brand:
                    raise ValueError("Il record non appartiene al brand selezionato")
                existing["brand_raw"] = brand_raw
                existing["updated_at"] = datetime.now(timezone.utc).isoformat()
                saved = existing
            else:
                with _connection() as connection:
                    if not _source_record_exists(
                        connection,
                        source,
                        record_key_expression,
                        record_key,
                        brand,
                    ):
                        raise ValueError("Occorrenza brand_raw non trovata")
                saved = {
                    "record_key": record_key,
                    "source_key": record_key,
                    "brand": brand,
                    "brand_raw": brand_raw,
                    "is_new": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                rows.append(saved)
            _write_edits(edits_path, rows)
    except Timeout as exc:
        raise ValueError("Archivio modifiche occupato; riprovare") from exc

    return {"row": _saved_row(saved), "edits_file": edits_path.name}


def create_brand_raw(brand: str, brand_raw: str) -> dict[str, Any]:
    brand = _normalize_text(brand, "brand")
    brand_raw = _normalize_text(brand_raw, "brand_raw")
    source_path = brands_dictionary_path()
    columns = _schema(_stamp(source_path))
    source, _ = _source_query(source_path, columns)
    edits_path = brands_edits_path()

    try:
        with FileLock(str(edits_path) + ".lock", timeout=30):
            with _connection() as connection:
                if not _source_brand_exists(connection, source, brand):
                    raise ValueError("Brand non trovato nel Brands Dictionary")
            rows = _read_edits(edits_path).to_pylist()
            saved = {
                "record_key": f"new:{uuid4().hex}",
                "source_key": None,
                "brand": brand,
                "brand_raw": brand_raw,
                "is_new": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(saved)
            _write_edits(edits_path, rows)
    except Timeout as exc:
        raise ValueError("Archivio modifiche occupato; riprovare") from exc

    return {"row": _saved_row(saved), "edits_file": edits_path.name}
