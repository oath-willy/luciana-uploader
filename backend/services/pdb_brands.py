from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb

from services.items_code_browse_cache import QUERY_SLOTS
from services.mc_code_local_store import SnapshotUnavailable
from services.pdb_brands_dictionary_sync import brands_dictionary_path


REQUIRED_COLUMNS = frozenset({"id", "brand", "prefix", "brand_raw"})
BRAND_FILTERS = frozenset({"brand", "prefix"})
RAW_FILTERS = frozenset({"brand_raw"})


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
    source = f"read_parquet({_literal(str(path))})"
    base = f"""
        WITH occurrences AS (
            SELECT
                id,
                TRIM(CAST(brand_raw AS VARCHAR)) AS brand_raw
            FROM {source}
            WHERE TRIM(CAST(brand AS VARCHAR)) = ?
                AND brand_raw IS NOT NULL
                AND TRIM(CAST(brand_raw AS VARCHAR)) <> ''
        )
    """
    parameters = [brand, *filter_parameters]
    with _connection() as connection:
        total = connection.execute(
            base + "SELECT COUNT(*) FROM occurrences" + filter_where,
            parameters,
        ).fetchone()[0]
        rows = _read_rows(
            connection,
            base
            + "SELECT id, brand_raw FROM occurrences"
            + filter_where
            + " ORDER BY lower(brand_raw), brand_raw, id "
            + "LIMIT ? OFFSET ?",
            [*parameters, page_size, page * page_size],
        )
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}
