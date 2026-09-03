from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal


CodexEnvironmentName = Literal["dev", "prod"]
CodexView = Literal["light", "full"]
MAX_EXTRA_COLUMNS = 12
_RUNTIME_SCHEMA_LOCK = threading.Lock()
_RUNTIME_INITIALIZED: set[Path] = set()


class SnapshotUnavailable(RuntimeError):
    pass


class SnapshotValidationError(ValueError):
    pass


def codex_data_dir() -> Path:
    configured = os.getenv("CODEX_LOCAL_DATA_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
    elif os.getenv("WEBSITE_SITE_NAME") or os.getenv("WEBSITE_INSTANCE_ID"):
        path = Path("/home/data/codex")
    else:
        path = Path(__file__).resolve().parents[1] / "data" / "codex"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_path(environment: CodexEnvironmentName) -> Path:
    return codex_data_dir() / f"snapshot-{environment}.sqlite3"


def runtime_path() -> Path:
    configured = os.getenv("CODEX_RUNTIME_DB", "").strip()
    return Path(configured).expanduser() if configured else codex_data_dir() / "runtime.sqlite3"


def environment_descriptors() -> list[dict[str, Any]]:
    result = []
    for value, label in (("dev", "Dev"), ("prod", "Prod")):
        path = snapshot_path(value)  # type: ignore[arg-type]
        result.append(
            {
                "value": value,
                "label": label,
                "available": path.is_file(),
                "message": None
                if path.is_file()
                else f"Snapshot locale CODEX non disponibile ({path.name})",
            }
        )
    return result


class CodexSnapshotStore:
    def __init__(self, environment: CodexEnvironmentName):
        self.environment = environment
        self.path = snapshot_path(environment)

    def metadata(self) -> dict[str, str]:
        with self._connect() as connection:
            return {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM metadata")
            }

    def companies(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT company, full_view_available, full_view_message
                FROM companies
                ORDER BY company COLLATE NOCASE
                """
            ).fetchall()
        return [
            {
                "value": row["company"],
                "label": row["company"],
                "full_view_available": bool(row["full_view_available"]),
                "full_view_message": row["full_view_message"],
            }
            for row in rows
        ]

    def search(
        self,
        company: str,
        view: CodexView,
        page: int,
        page_size: int,
        search: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        extra_columns = self._extra_columns(company) if view == "full" else []
        allowed = {
            "company_item_code",
            "item_code",
            "description",
            *(column["field"] for column in extra_columns),
        }
        unknown = sorted(set(filters) - allowed)
        if unknown:
            raise ValueError(f"Filtro CODEX non supportato: {unknown[0]}")

        clauses = ["UPPER(company) = UPPER(?)"]
        parameters: list[Any] = [company.strip()]
        if search.strip():
            value = f"%{_escape_like(search.strip())}%"
            clauses.append(
                "(company_item_code LIKE ? ESCAPE '\\' COLLATE NOCASE "
                "OR item_code LIKE ? ESCAPE '\\' COLLATE NOCASE "
                "OR description LIKE ? ESCAPE '\\' COLLATE NOCASE "
                "OR details_json LIKE ? ESCAPE '\\' COLLATE NOCASE)"
            )
            parameters.extend([value, value, value, value])
        for field, raw_value in filters.items():
            value = str(raw_value or "").strip()
            if not value:
                continue
            expression = (
                field
                if field in {"company_item_code", "item_code", "description"}
                else "json_extract(details_json, ?)"
            )
            if expression.startswith("json_extract"):
                parameters.append(f'$.{field}')
            clauses.append(f"CAST({expression} AS TEXT) LIKE ? ESCAPE '\\' COLLATE NOCASE")
            parameters.append(f"%{_escape_like(value)}%")

        where = " AND ".join(clauses)
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS total FROM items WHERE {where}", parameters
            ).fetchone()["total"]
            rows = connection.execute(
                f"""
                SELECT * FROM items
                WHERE {where}
                ORDER BY company_item_code COLLATE NOCASE, item_code COLLATE NOCASE
                LIMIT ? OFFSET ?
                """,
                [*parameters, page_size, page * page_size],
            ).fetchall()

        result_rows = [self._deserialize_item(row, view) for row in rows]
        RuntimeStore().enrich_rows(self.environment, company, result_rows)
        return {"rows": result_rows, "total": int(total), "extra_columns": extra_columns}

    def detail(self, company: str, item_code: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM items
                WHERE UPPER(company) = UPPER(?) AND item_code = ?
                """,
                (company.strip(), item_code.strip()),
            ).fetchone()
        if row is None:
            return None
        item = self._deserialize_item(row, "full")
        RuntimeStore().enrich_rows(self.environment, company, [item])
        return {"record": item, "extra_columns": self._extra_columns(company)}

    def get_items(self, company: str, item_codes: Iterable[str]) -> list[dict[str, Any]]:
        normalized = list(dict.fromkeys(str(value).strip() for value in item_codes if str(value).strip()))
        if not normalized:
            return []
        placeholders = ",".join("?" for _ in normalized)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM items
                WHERE UPPER(company) = UPPER(?) AND item_code IN ({placeholders})
                """,
                [company.strip(), *normalized],
            ).fetchall()
        by_code = {row["item_code"]: self._deserialize_item(row, "full") for row in rows}
        result = [by_code[code] for code in normalized if code in by_code]
        RuntimeStore().enrich_rows(self.environment, company, result)
        return result

    def eligible(
        self,
        company: str,
        view: CodexView,
        search: str,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        page = 0
        result: list[dict[str, Any]] = []
        while True:
            response = self.search(company, view, page, 500, search, filters)
            result.extend(
                row
                for row in response["rows"]
                if _has_three_bs25_proposals(row)
                and not row.get("aibs25_status")
                and not row.get("bs25_selection_status")
                and not row.get("bs25_selected_source")
            )
            page += 1
            if page * 500 >= response["total"]:
                return result

    def has_master_code(self, master_code: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM master_codes WHERE UPPER(master_code) = UPPER(?) LIMIT 1",
                (master_code.strip(),),
            ).fetchone()
        return row is not None

    def master_code_components(self, master_code: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT components_json FROM master_codes WHERE UPPER(master_code) = UPPER(?)",
                (master_code.strip(),),
            ).fetchone()
        return _loads(row["components_json"], {}) if row else None

    def all_master_codes(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT master_code, components_json FROM master_codes ORDER BY master_code"
            ).fetchall()
        return [
            {
                "master_code": row["master_code"],
                "components": _loads(row["components_json"], {}),
            }
            for row in rows
        ]

    def _extra_columns(self, company: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT extra_columns_json FROM companies WHERE UPPER(company) = UPPER(?)",
                (company.strip(),),
            ).fetchone()
        columns = _loads(row["extra_columns_json"], []) if row else []
        return columns[:MAX_EXTRA_COLUMNS]

    def _deserialize_item(self, row: sqlite3.Row, view: CodexView) -> dict[str, Any]:
        result = {
            "id": f'{row["company"]}::{row["item_code"]}',
            "company": row["company"],
            "item_code": row["item_code"],
            "company_item_code": row["company_item_code"],
            "description": row["description"],
            "bs25_status": row["bs25_status"],
            "bs25_proposal_1": _loads(row["proposal_1_json"], None),
            "bs25_proposal_2": _loads(row["proposal_2_json"], None),
            "bs25_proposal_3": _loads(row["proposal_3_json"], None),
        }
        if row["selected_proposal_rank"] is not None or row["selected_master_code"]:
            result.update(
                {
                    "bs25_selected_source": "snapshot",
                    "bs25_selected_proposal_rank": row["selected_proposal_rank"],
                    "bs25_selected_master_code": row["selected_master_code"],
                    "bs25_selection_status": row["selection_status"] or "completed",
                }
            )
        if view == "full":
            result.update(_loads(row["details_json"], {}))
        return result

    @contextmanager
    def _connect(self):
        if not self.path.is_file():
            raise SnapshotUnavailable(
                f"Snapshot locale CODEX non disponibile: {self.path}"
            )
        connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()


class RuntimeStore:
    def __init__(self, path: Path | None = None):
        self.path = path or runtime_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_job(
        self,
        environment: str,
        company: str,
        item_code: str,
        request_id: str,
        requested_by: str,
    ) -> bool:
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT status FROM aibs25_jobs
                WHERE environment=? AND UPPER(company)=UPPER(?) AND item_code=?
                """,
                (environment, company, item_code),
            ).fetchone()
            if existing and existing["status"] in {"queued", "analyzing", "completed"}:
                return False
            connection.execute(
                """
                INSERT INTO aibs25_jobs (
                    environment, company, item_code, request_id, status, stage,
                    requested_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', 'routing', ?, ?, ?)
                ON CONFLICT(environment, company, item_code) DO UPDATE SET
                    request_id=excluded.request_id, status='queued', stage='routing',
                    error_message=NULL, requested_by=excluded.requested_by,
                    updated_at=excluded.updated_at
                """,
                (environment, company, item_code, request_id, requested_by, now, now),
            )
            connection.commit()
        return True

    def create_bs25_job(
        self,
        environment: str,
        company: str,
        item_code: str,
        request_id: str,
        requested_by: str,
    ) -> bool:
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT status FROM local_bs25_results
                WHERE environment=? AND UPPER(company)=UPPER(?) AND item_code=?
                """,
                (environment, company, item_code),
            ).fetchone()
            if existing and existing["status"] in {"queued", "analyzing"}:
                return False
            connection.execute(
                """
                INSERT INTO local_bs25_results (
                    environment, company, item_code, request_id, status,
                    requested_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)
                ON CONFLICT(environment, company, item_code) DO UPDATE SET
                    request_id=excluded.request_id,
                    status='queued',
                    proposal_1_json=NULL,
                    proposal_2_json=NULL,
                    proposal_3_json=NULL,
                    retriever_version=NULL,
                    error_message=NULL,
                    requested_by=excluded.requested_by,
                    updated_at=excluded.updated_at
                """,
                (environment, company, item_code, request_id, requested_by, now, now),
            )
            connection.commit()
        return True

    def update_bs25_job(
        self, environment: str, company: str, item_code: str, **values: Any
    ) -> None:
        allowed = {
            "status",
            "proposal_1_json",
            "proposal_2_json",
            "proposal_3_json",
            "retriever_version",
            "error_message",
        }
        payload = {key: value for key, value in values.items() if key in allowed}
        for key in ("proposal_1_json", "proposal_2_json", "proposal_3_json"):
            if key in payload and not isinstance(payload[key], str):
                payload[key] = _dumps_optional(payload[key])
        payload["updated_at"] = _utc_now()
        assignments = ", ".join(f"{key}=?" for key in payload)
        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE local_bs25_results SET {assignments}
                WHERE environment=? AND UPPER(company)=UPPER(?) AND item_code=?
                """,
                [*payload.values(), environment, company, item_code],
            )
            connection.commit()

    def update_job(self, environment: str, company: str, item_code: str, **values: Any) -> None:
        allowed = {
            "status",
            "stage",
            "route",
            "thread_id",
            "goal_status",
            "taxonomy_coherent",
            "flag",
            "result_json",
            "error_message",
        }
        payload = {key: value for key, value in values.items() if key in allowed}
        if "result_json" in payload and not isinstance(payload["result_json"], str):
            payload["result_json"] = json.dumps(payload["result_json"], ensure_ascii=False)
        payload["updated_at"] = _utc_now()
        assignments = ", ".join(f"{key}=?" for key in payload)
        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE aibs25_jobs SET {assignments}
                WHERE environment=? AND UPPER(company)=UPPER(?) AND item_code=?
                """,
                [*payload.values(), environment, company, item_code],
            )
            connection.commit()

    def get_job(self, environment: str, company: str, item_code: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM aibs25_jobs
                WHERE environment=? AND UPPER(company)=UPPER(?) AND item_code=?
                """,
                (environment, company, item_code),
            ).fetchone()
        return self._job_dict(row) if row else None

    def save_selection(
        self,
        environment: str,
        company: str,
        item_code: str,
        kind: str,
        proposal_rank: int | None,
        master_code: str | None,
        request_id: str,
        selected_by: str,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as connection:
            if kind == "clear":
                connection.execute(
                    """
                    INSERT INTO selections (
                        environment, company, item_code, selection_kind, proposal_rank,
                        master_code, selection_request_id, selected_by, updated_at
                    ) VALUES (?, ?, ?, 'clear', NULL, NULL, ?, ?, ?)
                    ON CONFLICT(environment, company, item_code) DO UPDATE SET
                        selection_kind='clear', proposal_rank=NULL, master_code=NULL,
                        selection_request_id=excluded.selection_request_id,
                        selected_by=excluded.selected_by, updated_at=excluded.updated_at
                    """,
                    (environment, company, item_code, request_id, selected_by, now),
                )
                connection.commit()
                return {
                    "selection_status": "completed",
                    "selection_request_id": request_id,
                    "selection_kind": "clear",
                    "proposal_rank": None,
                    "master_code": None,
                    "selected": True,
                }
            connection.execute(
                """
                INSERT INTO selections (
                    environment, company, item_code, selection_kind, proposal_rank,
                    master_code, selection_request_id, selected_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(environment, company, item_code) DO UPDATE SET
                    selection_kind=excluded.selection_kind,
                    proposal_rank=excluded.proposal_rank,
                    master_code=excluded.master_code,
                    selection_request_id=excluded.selection_request_id,
                    selected_by=excluded.selected_by,
                    updated_at=excluded.updated_at
                """,
                (
                    environment,
                    company,
                    item_code,
                    kind,
                    proposal_rank,
                    master_code,
                    request_id,
                    selected_by,
                    now,
                ),
            )
            connection.commit()
        return {
            "selection_status": "completed",
            "selection_request_id": request_id,
            "selection_kind": kind,
            "proposal_rank": proposal_rank,
            "master_code": master_code,
            "selected": True,
        }

    def enrich_rows(self, environment: str, company: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        item_codes = [row["item_code"] for row in rows]
        placeholders = ",".join("?" for _ in item_codes)
        with self._connect() as connection:
            local_bs25 = connection.execute(
                f"""
                SELECT * FROM local_bs25_results
                WHERE environment=? AND UPPER(company)=UPPER(?)
                  AND item_code IN ({placeholders})
                """,
                [environment, company, *item_codes],
            ).fetchall()
            jobs = connection.execute(
                f"""
                SELECT * FROM aibs25_jobs
                WHERE environment=? AND UPPER(company)=UPPER(?)
                  AND item_code IN ({placeholders})
                """,
                [environment, company, *item_codes],
            ).fetchall()
            selections = connection.execute(
                f"""
                SELECT * FROM selections
                WHERE environment=? AND UPPER(company)=UPPER(?)
                  AND item_code IN ({placeholders})
                """,
                [environment, company, *item_codes],
            ).fetchall()
        local_bs25_by_code = {row["item_code"]: row for row in local_bs25}
        jobs_by_code = {row["item_code"]: self._job_dict(row) for row in jobs}
        selections_by_code = {row["item_code"]: row for row in selections}
        for result in rows:
            bs25 = local_bs25_by_code.get(result["item_code"])
            if bs25:
                result.update(
                    {
                        "bs25_status": bs25["status"],
                        "bs25_proposal_1": _loads(bs25["proposal_1_json"], None),
                        "bs25_proposal_2": _loads(bs25["proposal_2_json"], None),
                        "bs25_proposal_3": _loads(bs25["proposal_3_json"], None),
                        "bs25_retriever_version": bs25["retriever_version"],
                        "bs25_error_message": bs25["error_message"],
                    }
                )
            job = jobs_by_code.get(result["item_code"])
            if job:
                result.update({f"aibs25_{key}": value for key, value in job.items() if key not in {"environment", "company", "item_code"}})
            selection = selections_by_code.get(result["item_code"])
            if selection:
                if selection["selection_kind"] == "clear":
                    result.update(
                        {
                            "bs25_selected_source": None,
                            "bs25_selected_proposal_rank": None,
                            "bs25_selected_master_code": None,
                            "bs25_selection_request_id": selection["selection_request_id"],
                            "bs25_selection_status": None,
                            "bs25_selection_cleared": True,
                        }
                    )
                else:
                    result.update(
                        {
                            "bs25_selected_source": selection["selection_kind"],
                            "bs25_selected_proposal_rank": selection["proposal_rank"],
                            "bs25_selected_master_code": selection["master_code"],
                            "bs25_selection_request_id": selection["selection_request_id"],
                            "bs25_selection_status": "completed",
                        }
                    )

    def _job_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["taxonomy_coherent"] = (
            bool(result["taxonomy_coherent"])
            if result["taxonomy_coherent"] is not None
            else None
        )
        result["result"] = _loads(result.pop("result_json"), None)
        return result

    def _initialize(self) -> None:
        resolved_path = self.path.resolve()
        with _RUNTIME_SCHEMA_LOCK:
            if resolved_path in _RUNTIME_INITIALIZED:
                return
            with self._connect() as connection:
                connection.execute("PRAGMA busy_timeout=15000")
                connection.executescript(
                    """
                    PRAGMA journal_mode=WAL;
                    CREATE TABLE IF NOT EXISTS aibs25_jobs (
                        environment TEXT NOT NULL,
                        company TEXT NOT NULL,
                        item_code TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        route TEXT,
                        thread_id TEXT,
                        goal_status TEXT,
                        taxonomy_coherent INTEGER,
                        flag TEXT,
                        result_json TEXT,
                        error_message TEXT,
                        requested_by TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(environment, company, item_code)
                    );
                    CREATE TABLE IF NOT EXISTS selections (
                        environment TEXT NOT NULL,
                        company TEXT NOT NULL,
                        item_code TEXT NOT NULL,
                        selection_kind TEXT NOT NULL,
                        proposal_rank INTEGER,
                        master_code TEXT,
                        selection_request_id TEXT NOT NULL,
                        selected_by TEXT,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(environment, company, item_code)
                    );
                    CREATE TABLE IF NOT EXISTS local_bs25_results (
                        environment TEXT NOT NULL,
                        company TEXT NOT NULL,
                        item_code TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        proposal_1_json TEXT,
                        proposal_2_json TEXT,
                        proposal_3_json TEXT,
                        retriever_version TEXT,
                        error_message TEXT,
                        requested_by TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(environment, company, item_code)
                    );
                    """
                )
                connection.commit()
            _RUNTIME_INITIALIZED.add(resolved_path)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
        finally:
            connection.close()


def publish_snapshot(
    environment: CodexEnvironmentName,
    snapshot_id: str,
    created_at: str,
    companies: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    master_codes: list[dict[str, Any]],
) -> dict[str, Any]:
    if not snapshot_id.strip():
        raise SnapshotValidationError("snapshot_id obbligatorio")
    if not rows:
        raise SnapshotValidationError("Lo snapshot CODEX non contiene righe")
    declared_companies = {
        str(item.get("company") or "").strip().upper() for item in companies
    }
    row_companies = {str(item.get("company") or "").strip().upper() for item in rows}
    missing_companies = sorted(row_companies - declared_companies)
    if missing_companies:
        raise SnapshotValidationError(
            f"Company non dichiarata nello snapshot: {missing_companies[0]}"
        )

    target = snapshot_path(environment)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(
                """
                PRAGMA journal_mode=DELETE;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE companies (
                    company TEXT PRIMARY KEY COLLATE NOCASE,
                    full_view_available INTEGER NOT NULL,
                    full_view_message TEXT,
                    extra_columns_json TEXT NOT NULL
                );
                CREATE TABLE items (
                    environment TEXT NOT NULL,
                    company TEXT NOT NULL COLLATE NOCASE,
                    item_code TEXT NOT NULL,
                    company_item_code TEXT NOT NULL,
                    description TEXT,
                    details_json TEXT NOT NULL,
                    bs25_status TEXT,
                    proposal_1_json TEXT,
                    proposal_2_json TEXT,
                    proposal_3_json TEXT,
                    selected_proposal_rank INTEGER,
                    selected_master_code TEXT,
                    selection_status TEXT,
                    PRIMARY KEY(company, item_code)
                );
                CREATE INDEX items_company_code_idx ON items(company, company_item_code);
                CREATE TABLE master_codes (
                    master_code TEXT PRIMARY KEY COLLATE NOCASE,
                    components_json TEXT NOT NULL
                );
                """
            )
            connection.executemany(
                "INSERT INTO metadata(key,value) VALUES (?,?)",
                [
                    ("snapshot_id", snapshot_id.strip()),
                    ("created_at", created_at),
                    ("published_at", _utc_now()),
                    ("environment", environment),
                ],
            )
            connection.executemany(
                """
                INSERT INTO companies(company,full_view_available,full_view_message,extra_columns_json)
                VALUES (?,?,?,?)
                """,
                [
                    (
                        str(item["company"]).strip().upper(),
                        int(bool(item.get("full_view_available", False))),
                        item.get("full_view_message"),
                        json.dumps(item.get("extra_columns", []), ensure_ascii=False),
                    )
                    for item in companies
                ],
            )
            seen: set[tuple[str, str]] = set()
            serialized_rows = []
            for item in rows:
                company = str(item.get("company") or "").strip().upper()
                item_code = str(item.get("item_code") or "").strip()
                if not company or not item_code:
                    raise SnapshotValidationError("Ogni riga richiede company e item_code")
                key = (company, item_code)
                if key in seen:
                    raise SnapshotValidationError(f"Riga duplicata nello snapshot: {company}|{item_code}")
                seen.add(key)
                serialized_rows.append(
                    (
                        environment,
                        company,
                        item_code,
                        str(item.get("company_item_code") or f"{company}|{item_code}"),
                        item.get("description"),
                        json.dumps(item.get("details", {}), ensure_ascii=False),
                        item.get("bs25_status"),
                        _dumps_optional(item.get("bs25_proposal_1")),
                        _dumps_optional(item.get("bs25_proposal_2")),
                        _dumps_optional(item.get("bs25_proposal_3")),
                        item.get("bs25_selected_proposal_rank"),
                        item.get("bs25_selected_master_code"),
                        item.get("bs25_selection_status"),
                    )
                )
            connection.executemany(
                """
                INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                serialized_rows,
            )
            distinct_master_codes: dict[str, dict[str, Any]] = {}
            for item in master_codes:
                code = str(item.get("master_code") or "").strip().upper()
                if code:
                    distinct_master_codes[code] = item.get("components", {})
            connection.executemany(
                "INSERT INTO master_codes(master_code,components_json) VALUES (?,?)",
                [
                    (
                        code,
                        json.dumps(components, ensure_ascii=False),
                    )
                    for code, components in distinct_master_codes.items()
                ],
            )
            check = connection.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise SnapshotValidationError(f"SQLite quick_check fallito: {check}")
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "environment": environment,
        "snapshot_id": snapshot_id.strip(),
        "rows": len(rows),
        "companies": len(companies),
        "master_codes": len(distinct_master_codes),
        "path": str(target),
    }


def _has_three_bs25_proposals(row: dict[str, Any]) -> bool:
    return row.get("bs25_status") == "completed" and all(
        isinstance(row.get(f"bs25_proposal_{rank}"), dict) for rank in (1, 2, 3)
    )


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _dumps_optional(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
