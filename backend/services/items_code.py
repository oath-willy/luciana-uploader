from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation
from array import array
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import duckdb
import pyarrow as pa
from services.items_code_company_cache import companies as company_cache

from services.items_code_browse_cache import (
    COMPANY, MATCH_CACHE_BYTES, QUERY_SLOTS, ROW_ID, SEARCH_TEXT, matches, ready_snapshot,
)
from services.mc_code_local_store import RuntimeStore, SnapshotUnavailable
from services.pdb_new_items_sync import new_items_path
from services.pdb_ref_sync import pdb_ref_local_path


Dataset = Literal["new-items", "pdb"]
JSON_FIELD = "item_extra_descriptions"
MC_FIELDS = ("mc_lvl1_code", "mc_lvl2_code", "mc_lvl3_code")
SUPPORT_FIELDS = (
    ("prefix_code", "VARCHAR"), ("father_name", "VARCHAR"), ("master_code", "VARCHAR"),
    ("pack", "VARCHAR"), ("inner_count", "DECIMAL(18,6)"), ("inner_qty", "DECIMAL(18,6)"),
    ("pack_measure_unit", "VARCHAR"), ("feature", "VARCHAR"), ("measure", "VARCHAR"), ("extra", "VARCHAR"),
)
SUPPORT_EXCLUDED = {"company_item_code", "description", "dealer_company_name", "brand_name", "brand_prefix", "last_update"}
EDITABLE_FIELDS = frozenset(field for field, _ in SUPPORT_FIELDS)


def dataset_path(dataset: Dataset) -> Path:
    if dataset == "new-items":
        return new_items_path()
    configured = os.getenv("ITEMS_CODE_PDB_LOCAL_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return pdb_ref_local_path()


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@contextmanager
def _query_connection():
    with QUERY_SLOTS, duckdb.connect(config={"threads": 2, "memory_limit": "128MB"}) as connection:
        connection.execute("SET enable_progress_bar = false")
        yield connection


@contextmanager
def _connect(path: Path):
    if not path.is_file():
        raise SnapshotUnavailable(f"File {path.name} assente. Recuperarlo da PDB Settings.")
    with _query_connection() as connection:
        connection.execute(f"CREATE VIEW source AS SELECT * FROM read_parquet({_literal(str(path))}, file_row_number=true)")
        yield connection


def _stamp(path: Path) -> tuple[str, int, int]:
    if not path.is_file():
        raise SnapshotUnavailable(f"File {path.name} assente. Recuperarlo da PDB Settings.")
    stat = path.stat()
    return str(path.resolve()), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=16)
def _schema(stamp: tuple[str, int, int]) -> tuple[tuple[str, str], ...]:
    with _connect(Path(stamp[0])) as connection:
        fields = tuple((row[0], row[1]) for row in connection.execute("DESCRIBE source").fetchall() if row[0] != "file_row_number")
    for name, _ in fields:
        if name in (ROW_ID, COMPANY, SEARCH_TEXT):
            raise ValueError(f"Colonna riservata: {name}")
    return fields


def _company_expression(fields: tuple[tuple[str, str], ...]) -> str:
    names = {name for name, _ in fields}
    for name in ("company", "dealer_company_name"):
        if name in names:
            return f"UPPER(TRIM(CAST({_identifier(name)} AS VARCHAR)))"
    for name in ("company_item_code", "pdb_ref"):
        if name in names:
            return f"UPPER(TRIM(split_part({_identifier(name)}, '|', 1)))"
    raise ValueError("Il file PDB non contiene un campo Company o un riferimento company|item_code")


@lru_cache(maxsize=16)
def _companies(stamp: tuple[str, int, int]) -> tuple[str, ...]:
    expression = _company_expression(_schema(stamp))
    with _connect(Path(stamp[0])) as connection:
        rows = connection.execute(
            f"SELECT DISTINCT {expression} AS company FROM source WHERE {expression} IS NOT NULL AND {expression} <> '' ORDER BY company"
        ).fetchall()
    return tuple(row[0] for row in rows)


@lru_cache(maxsize=64)
def _extra_keys(stamp: tuple[str, int, int], company: str) -> tuple[str, ...]:
    fields = _schema(stamp)
    if JSON_FIELD not in {name for name, _ in fields}:
        return ()
    expression = _company_expression(fields)
    with _connect(Path(stamp[0])) as connection:
        rows = connection.execute(
            f"SELECT DISTINCT j.key FROM source, json_each({_identifier(JSON_FIELD)}) j WHERE {expression} = ? ORDER BY j.key",
            [company],
        ).fetchall()
    return tuple(row[0] for row in rows)


def _columns(stamp: tuple[str, int, int], dataset: Dataset, company: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    fields = _schema(stamp)
    columns = [{"field": name, "header_name": name.replace("_", " ").title(), "data_type": kind} for name, kind in fields]
    expressions = {name: _identifier(name) for name, _ in fields}
    if dataset == "pdb" and all(name in expressions for name in MC_FIELDS):
        position = next(index for index, column in enumerate(columns) if column["field"] == MC_FIELDS[0])
        parts = [f"TRY_CAST({_identifier(name)} AS INTEGER)" for name in MC_FIELDS]
        valid = " AND ".join(f"{part} BETWEEN 0 AND 99" for part in parts)
        columns = [column for column in columns if column["field"] not in MC_FIELDS]
        columns.insert(position, {"field": "master_code", "header_name": "Master Code", "data_type": "VARCHAR"})
        for name in MC_FIELDS:
            del expressions[name]
        expressions["master_code"] = f"CASE WHEN {valid} THEN printf('%02d_%02d_%02d', {', '.join(parts)}) ELSE NULL END"
    if dataset == "new-items":
        if "company_item_code" not in expressions:
            columns.insert(2, {"field": "company_item_code", "header_name": "Company Item Code", "data_type": "VARCHAR"})
            expressions["company_item_code"] = "concat(company, '|', item_code)"
        for key in _extra_keys(stamp, company):
            field = f"{JSON_FIELD}.{key}"
            if field in expressions:
                raise ValueError(f"Colonna JSON duplicata: {field}")
            path = '$.' + json.dumps(key, ensure_ascii=False)
            columns.append({"field": field, "header_name": key.replace("_", " ").title(), "data_type": "JSON"})
            expressions[field] = f"json_extract({_identifier(JSON_FIELD)}, {_literal(path)})"
        reference = dataset_path("pdb")
        if reference.is_file():
            reference_columns, _ = _columns(_stamp(reference), "pdb", "")
        else:
            reference_columns = [{"field": name, "header_name": name.replace("_", " ").title(), "data_type": kind}
                                 for name, kind in SUPPORT_FIELDS]
        for column in reference_columns:
            field = column["field"]
            if field not in SUPPORT_EXCLUDED and field not in expressions:
                columns.append(column.copy())
                expressions[field] = f"CAST(NULL AS {column['data_type']})"
        for column in columns:
            column["editable"] = column["field"] in EDITABLE_FIELDS
    return columns, expressions


def dataset_metadata(dataset: Dataset, company: str = "") -> dict[str, Any]:
    path = dataset_path(dataset)
    if not path.is_file():
        return {"available": False, "source_file": path.name, "companies": [], "columns": [], "message": f"Recuperare {path.name} da PDB Settings."}
    stamp = _stamp(path)
    columns, _ = _columns(stamp, dataset, company.strip().upper())
    return {"available": True, "source_file": path.name, "companies": list(_companies(stamp)), "columns": columns, "message": None}


def search_dataset(dataset: Dataset, company: str, page: int, page_size: int, search: str, filters: dict[str, str]) -> dict[str, Any]:
    company = company.strip().upper()
    if dataset == "new-items" and not company:
        raise ValueError("Selezionare una Company per i New Items")
    path = dataset_path(dataset)
    stamp = _stamp(path)
    columns, expressions = _columns(stamp, dataset, company)
    unknown = set(filters) - set(expressions)
    if unknown:
        raise ValueError(f"Filtro non supportato: {sorted(unknown)[0]}")
    company_table = None
    if dataset == "new-items":
        key = (stamp, company, tuple(expressions.items()))
        def load_company():
            projection = ', '.join(f"{expression} AS {_identifier(field)}" for field, expression in expressions.items())
            with _connect(path) as connection:
                return connection.execute(
                    f"SELECT file_row_number AS {_identifier(ROW_ID)}, {projection} FROM source "
                    f"WHERE {_company_expression(_schema(stamp))}=?", [company]
                ).fetch_arrow_table()
        company_table = company_cache.get(key, load_company)
        expressions = {field: _identifier(field) for field in expressions}
    edits = RuntimeStore().items_code_edits(company) if dataset == "new-items" else {}
    if edits:
        # Test key presence separately: an explicit JSON null must clear the source value.
        for column in columns:
            field = column["field"]
            if field in EDITABLE_FIELDS:
                json_path = _literal('$."' + field + '"')
                expressions[field] = (
                    f"CASE WHEN json_exists(__items_code_patch, {json_path}) "
                    f"THEN CAST(json_extract_string(__items_code_patch, {json_path}) AS {column['data_type']}) "
                    f"ELSE {expressions[field]} END"
                )
    unknown = set(filters) - set(expressions)
    if unknown:
        raise ValueError(f"Filtro non supportato: {sorted(unknown)[0]}")
    query_path = path
    row_id = _identifier(ROW_ID) if company_table is not None else "file_row_number"
    company_expression = _company_expression(_schema(stamp))
    prepared = None
    if dataset == "pdb":
        prepared = ready_snapshot(path, expressions, company_expression)
        if prepared:
            query_path = prepared
            expressions = {field: _identifier(field) for field in expressions}
            row_id = _identifier(ROW_ID)
            company_expression = _identifier(COMPANY)
    clauses: list[str] = []
    parameters: list[Any] = []
    if company and company_table is None:
        clauses.append(company_expression + " = ?")
        parameters.append(company)
    if search.strip():
        if prepared and "\x00" not in search:
            clauses.append(f"{_identifier(SEARCH_TEXT)} ILIKE ? ESCAPE '\\'")
            parameters.append(_like(search))
        else:
            clauses.append("(" + " OR ".join(f"CAST({expression} AS VARCHAR) ILIKE ? ESCAPE '\\'" for expression in expressions.values()) + ")")
            parameters.extend([_like(search)] * len(expressions))
    for field, value in sorted(filters.items()):
        if value.strip():
            clauses.append(f"CAST({expressions[field]} AS VARCHAR) ILIKE ? ESCAPE '\\'")
            parameters.append(_like(value))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    projection = ", ".join(f"{expression} AS {_identifier(field)}" for field, expression in expressions.items())
    if dataset == "pdb":
        total, rows = _reference_page(stamp, query_path, row_id, projection, where, parameters, page, page_size)
    else:
        with _query_connection() as connection:
            connection.register("company_source", company_table)
            connection.execute("CREATE OR REPLACE VIEW source AS SELECT * FROM company_source")
            if edits:
                connection.register("edit_overlay", pa.table({"item_code": list(edits), "patch": [json.dumps(v) for v in edits.values()]}))
                connection.execute("CREATE OR REPLACE VIEW source AS SELECT company_source.*, edit_overlay.patch AS __items_code_patch "
                                   "FROM company_source LEFT JOIN edit_overlay ON company_source.item_code=edit_overlay.item_code")
            total = company_table.num_rows if not where else connection.execute(f"SELECT COUNT(*) FROM source{where}", parameters).fetchone()[0]
            rows = _read_rows(connection, f"SELECT {row_id} AS {_identifier(ROW_ID)}, {projection} FROM source{where} "
                              f"ORDER BY {row_id} LIMIT ? OFFSET ?", [*parameters, page_size, page * page_size])
    for row in rows:
        for column in columns:
            if column["data_type"] == "JSON" and row[column["field"]] is not None:
                row[column["field"]] = json.loads(row[column["field"]])
    return {"rows": rows, "total": total, "columns": columns, "source_file": path.name}


@lru_cache(maxsize=16)
def _row_count(stamp: tuple[str, int, int], query_path: str) -> int:
    with _connect(Path(query_path)) as connection:
        # DuckDB answers an unfiltered count directly from the Parquet footer.
        return connection.execute("SELECT COUNT(*) FROM source").fetchone()[0]


def _matching_ids(path: Path, row_id: str, where: str, parameters: list[Any]) -> tuple[int, array | None]:
    identifiers = array("I")
    total = 0
    with _connect(path) as connection:
        cursor = connection.execute(f"SELECT {row_id} FROM source{where} ORDER BY {row_id}", parameters)
        while batch := cursor.fetchmany(8192):
            total += len(batch)
            if identifiers is not None:
                needs_wide_ids = batch[-1][0] >= 2**32
                itemsize = 8 if needs_wide_ids else identifiers.itemsize
                if (len(identifiers) + len(batch)) * itemsize <= MATCH_CACHE_BYTES:
                    if needs_wide_ids and identifiers.typecode == "I":
                        identifiers = array("Q", identifiers)
                    identifiers.extend(row[0] for row in batch)
                else:
                    identifiers = None
    return total, identifiers


def _reference_page(stamp: tuple[str, int, int], path: Path, row_id: str, projection: str,
                    where: str, parameters: list[Any], page: int, page_size: int) -> tuple[int, list[dict[str, Any]]]:
    offset = page * page_size
    if where:
        key = (stamp, str(path), where, tuple(parameters))
        total, identifiers = matches.get(key, lambda: _matching_ids(path, row_id, where, parameters))
        if identifiers is None:
            with _connect(path) as connection:
                identifiers = [row[0] for row in connection.execute(
                    f"SELECT {row_id} FROM source{where} ORDER BY {row_id} LIMIT ? OFFSET ?",
                    [*parameters, page_size, offset]).fetchall()]
        else:
            identifiers = identifiers[offset:offset + page_size]
        if not identifiers:
            return total, []
        # The range also enables row-group pruning; IN handles noncontiguous matches.
        predicate = f"{row_id} BETWEEN ? AND ? AND {row_id} IN ({', '.join('?' for _ in identifiers)})"
        page_parameters = [identifiers[0], identifiers[-1], *identifiers]
    else:
        total = _row_count(stamp, str(path))
        if offset >= total:
            return total, []
        predicate = f"{row_id} BETWEEN ? AND ?"
        page_parameters = [offset, min(offset + page_size, total) - 1]
    with _connect(path) as connection:
        rows = _read_rows(connection, f"SELECT {row_id} AS {_identifier(ROW_ID)}, {projection} "
                          f"FROM source WHERE {predicate} ORDER BY {row_id}", page_parameters)
    return total, rows


def _read_rows(connection, sql: str, parameters: list[Any]) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, parameters)
    names = [field[0] for field in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _like(value: str) -> str:
    return "%" + value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def save_new_item_values(company: str, item_codes: list[str], values: dict[str, Any]) -> dict[str, Any]:
    company = company.strip().upper()
    if not company or not item_codes or not values:
        raise ValueError("Company, record e valori sono obbligatori")
    item_codes = list(dict.fromkeys(item_codes))
    path = dataset_path("new-items")
    columns, _ = _columns(_stamp(path), "new-items", company)
    types = {column["field"]: column["data_type"] for column in columns if column["field"] in EDITABLE_FIELDS}
    if set(values) - set(types):
        raise ValueError("Si possono modificare solo i campi da Prefix Code in poi")
    normalized: dict[str, Any] = {}
    for field, value in values.items():
        if value is None or value == "":
            normalized[field] = None
        elif types[field].startswith("DECIMAL"):
            try:
                number = Decimal(str(value))
                precision, scale = map(int, re.findall(r"\d+", types[field]))
                if not number.is_finite() or abs(number) >= Decimal(10) ** (precision - scale) or number != number.quantize(Decimal(10) ** -scale):
                    raise ValueError()
                normalized[field] = format(number, "f")
            except (InvalidOperation, ValueError):
                raise ValueError(f"Valore numerico non valido per {field}") from None
        else:
            if not isinstance(value, (str, int, float)) or len(str(value)) > 16000:
                raise ValueError(f"Valore non valido per {field}")
            normalized[field] = str(value)
            if field == "master_code" and not re.fullmatch(r"\d{2}_\d{2}_\d{2}", normalized[field]):
                raise ValueError("Master Code deve avere formato 00_00_00")
    with _connect(path) as connection:
        placeholders = ', '.join('?' for _ in item_codes)
        rows = connection.execute(f"SELECT item_code FROM source WHERE {_company_expression(_schema(_stamp(path)))}=? "
                                  f"AND item_code IN ({placeholders})", [company, *item_codes]).fetchall()
    if {row[0] for row in rows} != set(item_codes):
        raise ValueError("Uno o piu record non appartengono alla Company selezionata o non esistono piu")
    RuntimeStore().save_items_code_edits(company, item_codes, normalized)
    return {"item_codes": item_codes, "values": normalized}
