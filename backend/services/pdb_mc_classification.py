from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from filelock import FileLock

from services.items_code_browse_cache import QUERY_SLOTS
from services.mc_code_local_store import SnapshotUnavailable
from services.pdb_mc_classification_sync import classification_path


KEY_FIELD = "master_code"
FAMILY_FIELD = "family"
SUBFAMILY_FIELD = "subfamily"
REQUIRED_COLUMNS = frozenset(
    {KEY_FIELD, "mc_desc", FAMILY_FIELD, SUBFAMILY_FIELD, "product_group"}
)
PAGE_SIZES = frozenset({25, 50, 100, 250, 500, 1000})
VIRTUAL_COLUMNS = frozenset({"__change_status", "__mc_classification_row_id"})
RUNTIME_FILE_NAME = "runtime_pdb_mc_classification.sqlite3"
LEGACY_EDITS_FILE_NAME = "pdb_mc_classification_edits.parquet"


def classification_runtime_path() -> Path:
    configured = os.getenv("PDB_MC_CLASSIFICATION_RUNTIME_DB", "").strip()
    source = classification_path()
    target = (
        Path(configured).expanduser()
        if configured
        else source.with_name(RUNTIME_FILE_NAME)
    )
    if source.is_file():
        _migrate_legacy_edits(source, target)
    return target


def _legacy_edits_path(source: Path) -> Path:
    configured = os.getenv("PDB_MC_CLASSIFICATION_EDITS_PATH", "").strip()
    return (
        Path(configured).expanduser()
        if configured
        else source.with_name(LEGACY_EDITS_FILE_NAME)
    )


def _migrate_legacy_edits(source: Path, target: Path) -> None:
    legacy = _legacy_edits_path(source)
    if target.is_file() or not legacy.is_file() or legacy == target:
        return
    with FileLock(str(target) + ".migration.lock", timeout=30):
        if target.is_file():
            return
        source_schema = pq.read_schema(source)
        table = pq.read_table(legacy)
        if table.schema != source_schema:
            raise ValueError(
                "Il vecchio file delle modifiche MC Classification non ha lo "
                "stesso schema della sorgente"
            )
        source_keys = {
            row[KEY_FIELD]
            for row in pq.read_table(source, columns=[KEY_FIELD]).to_pylist()
        }
        records = [
            (row, row[KEY_FIELD] not in source_keys)
            for row in table.to_pylist()
        ]
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}-migration-",
            suffix=".sqlite3",
            dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            _replace_runtime_records(temporary, records)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def _dataset_paths() -> tuple[Path, Path]:
    source = classification_path()
    runtime = classification_runtime_path()
    if source.resolve() == runtime.resolve():
        raise ValueError("Il file delle modifiche deve essere diverso dal file sorgente")
    return source, runtime


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


@lru_cache(maxsize=16)
def _schema(stamp: tuple[str, int, int]) -> tuple[tuple[str, str], ...]:
    path = Path(stamp[0])
    with _connection() as connection:
        fields = tuple(
            (row[0], row[1])
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet({_literal(str(path))})"
            ).fetchall()
        )
        names = {field for field, _ in fields}
        reserved = names & VIRTUAL_COLUMNS
        if reserved:
            raise ValueError(f"Colonna riservata: {sorted(reserved)[0]}")
        missing = REQUIRED_COLUMNS - names
        if missing:
            raise ValueError(
                "Il file MC Classification non contiene le colonne richieste: "
                + ", ".join(sorted(missing))
            )
        duplicate = connection.execute(
            f"""
            SELECT COUNT(*) - COUNT(DISTINCT {_identifier(KEY_FIELD)})
            FROM read_parquet({_literal(str(path))})
            """
        ).fetchone()[0]
        null_keys = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM read_parquet({_literal(str(path))})
            WHERE {_identifier(KEY_FIELD)} IS NULL
               OR TRIM(CAST({_identifier(KEY_FIELD)} AS VARCHAR)) = ''
            """
        ).fetchone()[0]
    if duplicate or null_keys:
        raise ValueError(
            "master_code deve essere valorizzato e univoco nel file MC Classification"
        )
    return fields


def _validated_schema(
    source_stamp: tuple[str, int, int],
) -> tuple[tuple[str, str], ...]:
    return _schema(source_stamp)


def _effective_cte(source: Path) -> str:
    source_sql = f"read_parquet({_literal(str(source))})"
    key = _identifier(KEY_FIELD)
    return f"""
        WITH source_rows AS (SELECT * FROM {source_sql}),
        edit_rows AS (SELECT * FROM classification_edits),
        effective AS (
            SELECT
                edited.*,
                CASE WHEN EXISTS (
                    SELECT 1 FROM source_rows original
                    WHERE original.{key} = edited.{key}
                ) THEN 'modified' ELSE 'added' END AS __change_status
            FROM edit_rows edited
            UNION ALL
            SELECT original.*, 'original' AS __change_status
            FROM source_rows original
            WHERE NOT EXISTS (
                SELECT 1 FROM edit_rows edited
                WHERE edited.{key} = original.{key}
            )
        )
    """


def _initialize_runtime(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS classification_edits (
            master_code TEXT PRIMARY KEY,
            values_json TEXT NOT NULL,
            is_new INTEGER NOT NULL CHECK(is_new IN (0, 1)),
            updated_at TEXT NOT NULL
        )
        """
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__runtime_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__runtime_type__": "date", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__runtime_type__": "decimal", "value": str(value)}
    if isinstance(value, bytes):
        return {
            "__runtime_type__": "bytes",
            "value": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _restore_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_restore_json_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    value_type = value.get("__runtime_type__")
    if value_type == "datetime":
        return datetime.fromisoformat(value["value"])
    if value_type == "date":
        return date.fromisoformat(value["value"])
    if value_type == "decimal":
        return Decimal(value["value"])
    if value_type == "bytes":
        return base64.b64decode(value["value"])
    return {key: _restore_json_value(item) for key, item in value.items()}


def _serialize_record(record: dict[str, Any]) -> str:
    return json.dumps(
        _json_value(record),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _runtime_records(
    path: Path,
    schema: tuple[tuple[str, str], ...],
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    columns = {field for field, _ in schema}
    with closing(sqlite3.connect(path, timeout=30)) as connection:
        connection.row_factory = sqlite3.Row
        _initialize_runtime(connection)
        rows = connection.execute(
            "SELECT master_code, values_json FROM classification_edits "
            "ORDER BY master_code"
        ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        record = _restore_json_value(json.loads(row["values_json"]))
        if not isinstance(record, dict) or set(record) != columns:
            raise ValueError(
                f"Schema non valido nel runtime MC Classification per {row['master_code']}"
            )
        if str(record.get(KEY_FIELD) or "") != row["master_code"]:
            raise ValueError("Chiave incoerente nel runtime MC Classification")
        records.append(record)
    return records


def _register_runtime(
    connection: duckdb.DuckDBPyConnection,
    source: Path,
    runtime: Path,
    schema: tuple[tuple[str, str], ...],
) -> None:
    table = pa.Table.from_pylist(
        _runtime_records(runtime, schema),
        schema=pq.read_schema(source),
    )
    connection.register("classification_edits", table)


def _replace_runtime_records(
    path: Path,
    records: list[tuple[dict[str, Any], bool]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as connection:
        _initialize_runtime(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM classification_edits")
        connection.executemany(
            """
            INSERT INTO classification_edits (
                master_code, values_json, is_new, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (
                    str(record[KEY_FIELD]),
                    _serialize_record(record),
                    int(is_new),
                    datetime.now(timezone.utc).isoformat(),
                )
                for record, is_new in records
            ],
        )
        connection.commit()


def _write_runtime_record(
    path: Path,
    record: dict[str, Any],
    is_new: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as connection:
        _initialize_runtime(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO classification_edits (
                master_code, values_json, is_new, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(master_code) DO UPDATE SET
                values_json=excluded.values_json,
                is_new=excluded.is_new,
                updated_at=excluded.updated_at
            """,
            (
                str(record[KEY_FIELD]),
                _serialize_record(record),
                int(is_new),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()


def _read_rows(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    parameters: list[Any],
) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, parameters)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def classification_metadata() -> dict[str, Any]:
    source, runtime = _dataset_paths()
    if not source.is_file():
        return {
            "available": False,
            "source_file": source.name,
            "runtime_file": runtime.name,
            "edits_file": runtime.name,
            "columns": [],
            "families": [],
            "subfamilies": [],
            "subfamilies_by_family": {},
            "message": f"Recuperare {source.name} da PDB Settings.",
        }

    schema = _validated_schema(_stamp(source))
    cte = _effective_cte(source)
    family = _identifier(FAMILY_FIELD)
    subfamily = _identifier(SUBFAMILY_FIELD)
    with _connection() as connection:
        _register_runtime(connection, source, runtime, schema)
        pairs = connection.execute(
            cte
            + f"""
                SELECT DISTINCT
                    TRIM(CAST({family} AS VARCHAR)) AS family,
                    TRIM(CAST({subfamily} AS VARCHAR)) AS subfamily
                FROM effective
                WHERE {family} IS NOT NULL
                  AND TRIM(CAST({family} AS VARCHAR)) <> ''
                ORDER BY lower(family), family, lower(subfamily), subfamily
            """
        ).fetchall()

    families: list[str] = []
    subfamilies: list[str] = []
    by_family: dict[str, list[str]] = {}
    for family_value, subfamily_value in pairs:
        if family_value not in by_family:
            families.append(family_value)
            by_family[family_value] = []
        if subfamily_value and subfamily_value not in by_family[family_value]:
            by_family[family_value].append(subfamily_value)
        if subfamily_value and subfamily_value not in subfamilies:
            subfamilies.append(subfamily_value)
    subfamilies.sort(key=str.casefold)

    return {
        "available": True,
        "source_file": source.name,
        "runtime_file": runtime.name,
        "edits_file": runtime.name,
        "primary_key": KEY_FIELD,
        "columns": [
            {
                "field": field,
                "header_name": field.replace("_", " ").title(),
                "data_type": data_type,
                "editable": field != KEY_FIELD,
            }
            for field, data_type in schema
        ],
        "families": families,
        "subfamilies": subfamilies,
        "subfamilies_by_family": by_family,
        "message": None,
    }


def search_classification(
    page: int,
    page_size: int,
    search: str,
    filters: dict[str, str],
    family: str = "",
    subfamily: str = "",
) -> dict[str, Any]:
    if page < 0:
        raise ValueError("page non puo essere negativa")
    if page_size not in PAGE_SIZES:
        raise ValueError("Rows per page non valido")

    source, runtime = _dataset_paths()
    schema = _validated_schema(_stamp(source))
    fields = [field for field, _ in schema]
    unknown = set(filters) - set(fields)
    if unknown:
        raise ValueError(f"Filtro non supportato: {sorted(unknown)[0]}")

    clauses: list[str] = []
    parameters: list[Any] = []
    if family.strip():
        clauses.append(
            f"TRIM(CAST({_identifier(FAMILY_FIELD)} AS VARCHAR)) = ?"
        )
        parameters.append(family.strip())
    if subfamily.strip():
        clauses.append(
            f"TRIM(CAST({_identifier(SUBFAMILY_FIELD)} AS VARCHAR)) = ?"
        )
        parameters.append(subfamily.strip())
    if search.strip():
        clauses.append(
            "("
            + " OR ".join(
                f"COALESCE(CAST({_identifier(field)} AS VARCHAR), '') ILIKE ? ESCAPE '\\'"
                for field in fields
            )
            + ")"
        )
        parameters.extend(_like(search) for _ in fields)
    for field, raw_value in sorted(filters.items()):
        value = str(raw_value).strip()
        if not value:
            continue
        clauses.append(
            f"COALESCE(CAST({_identifier(field)} AS VARCHAR), '') ILIKE ? ESCAPE '\\'"
        )
        parameters.append(_like(value))

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    cte = _effective_cte(source)
    key = _identifier(KEY_FIELD)
    with _connection() as connection:
        _register_runtime(connection, source, runtime, schema)
        total = connection.execute(
            cte + "SELECT COUNT(*) FROM effective" + where,
            parameters,
        ).fetchone()[0]
        rows = _read_rows(
            connection,
            cte
            + "SELECT * FROM effective"
            + where
            + f" ORDER BY lower(CAST({key} AS VARCHAR)), {key} LIMIT ? OFFSET ?",
            [*parameters, page_size, page * page_size],
        )

    for row in rows:
        row["__mc_classification_row_id"] = row[KEY_FIELD]
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


def _normalize_values(
    values: dict[str, Any],
    schema: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    allowed = {field for field, _ in schema}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Colonna non supportata: {sorted(unknown)[0]}")
    normalized: dict[str, Any] = {}
    for field, value in values.items():
        if value == "":
            normalized[field] = None
        elif isinstance(value, str):
            if len(value) > 16000:
                raise ValueError(f"Valore troppo lungo per {field}")
            normalized[field] = value.strip() if field == KEY_FIELD else value
        elif value is None or isinstance(value, (bool, int, float)):
            normalized[field] = value
        else:
            raise ValueError(f"Valore non valido per {field}")
    return normalized


def _effective_record(
    connection: duckdb.DuckDBPyConnection,
    source: Path,
    record_key: str,
) -> dict[str, Any] | None:
    rows = _read_rows(
        connection,
        _effective_cte(source)
        + f"SELECT * FROM effective WHERE {_identifier(KEY_FIELD)} = ?",
        [record_key],
    )
    return rows[0] if rows else None


def update_classification_record(
    record_key: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    record_key = record_key.strip()
    if not record_key or not values:
        raise ValueError("Record e valori sono obbligatori")
    if KEY_FIELD in values and str(values[KEY_FIELD]).strip() != record_key:
        raise ValueError("master_code non puo essere modificato")

    source, runtime = _dataset_paths()
    lock = FileLock(str(runtime) + ".lock", timeout=30)
    with lock:
        schema = _validated_schema(_stamp(source))
        normalized = _normalize_values(values, schema)
        normalized.pop(KEY_FIELD, None)
        if not normalized:
            raise ValueError("Nessun valore modificabile ricevuto")
        with _connection() as connection:
            _register_runtime(connection, source, runtime, schema)
            current = _effective_record(connection, source, record_key)
            if current is None:
                raise ValueError("Record MC Classification non trovato")
            is_new = current.pop("__change_status") == "added"
            current.update(normalized)
            try:
                pa.Table.from_pylist([current], schema=pq.read_schema(source))
            except (pa.ArrowException, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Uno dei valori non e compatibile con lo schema: {exc}"
                ) from exc
            _write_runtime_record(runtime, current, is_new)
    return {
        "row": current,
        "runtime_file": runtime.name,
        "edits_file": runtime.name,
    }


def create_classification_record(values: dict[str, Any]) -> dict[str, Any]:
    source, runtime = _dataset_paths()
    lock = FileLock(str(runtime) + ".lock", timeout=30)
    with lock:
        schema = _validated_schema(_stamp(source))
        normalized = _normalize_values(values, schema)
        record_key = str(normalized.get(KEY_FIELD) or "").strip()
        if not record_key:
            raise ValueError("master_code e obbligatorio")
        if not re.fullmatch(r"\d{2}_\d{2}_\d{2}", record_key):
            raise ValueError("master_code deve avere formato 00_00_00")
        record = {field: normalized.get(field) for field, _ in schema}
        record[KEY_FIELD] = record_key
        with _connection() as connection:
            _register_runtime(connection, source, runtime, schema)
            if _effective_record(connection, source, record_key) is not None:
                raise ValueError("Esiste gia un record con questo master_code")
            try:
                pa.Table.from_pylist([record], schema=pq.read_schema(source))
            except (pa.ArrowException, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Uno dei valori non e compatibile con lo schema: {exc}"
                ) from exc
            _write_runtime_record(runtime, record, True)
    return {
        "row": record,
        "runtime_file": runtime.name,
        "edits_file": runtime.name,
    }
