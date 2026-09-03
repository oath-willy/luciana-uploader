"""One-time/operator bootstrap of the local CODEX snapshots from Databricks.

This is a maintenance command, not application runtime code. It streams the
three approved Silver tables through the Databricks Statement Execution API,
builds only the current SQLite snapshots, and can publish them to the backend.
No raw table export or historical snapshot is retained.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from services.codex_local_retrieval import publish_pdb_snapshot  # noqa: E402
from services.codex_local_store import publish_snapshot  # noqa: E402


PRODUCTS_SQL = """
WITH latest_lookup AS (
    SELECT
        upper(trim(company)) AS company,
        trim(item_code) AS item_code,
        lookup_status AS bs25_status,
        proposal_1 AS bs25_proposal_1,
        proposal_2 AS bs25_proposal_2,
        proposal_3 AS bs25_proposal_3,
        selected_proposal_rank AS bs25_selected_proposal_rank,
        selected_master_code AS bs25_selected_master_code,
        selection_status AS bs25_selection_status,
        row_number() OVER (
            PARTITION BY upper(trim(company)), trim(item_code)
            ORDER BY requested_at DESC NULLS LAST
        ) AS lookup_rank
    FROM codex_bs25_lookup
)
SELECT
    upper(trim(p.company)) AS company,
    trim(p.item_code) AS item_code,
    concat(upper(trim(p.company)), '|', trim(p.item_code)) AS company_item_code,
    p.description,
    b.bs25_status,
    b.bs25_proposal_1,
    b.bs25_proposal_2,
    b.bs25_proposal_3,
    b.bs25_selected_proposal_rank,
    b.bs25_selected_master_code,
    b.bs25_selection_status,
    CAST(p.first_received_date AS STRING) AS first_received_date,
    p.source_file,
    p.search_type,
    p.status,
    CAST(p.created_date AS STRING) AS created_date
FROM product_to_classify p
LEFT JOIN latest_lookup b
    ON upper(trim(p.company)) = b.company
    AND trim(p.item_code) = b.item_code
    AND b.lookup_rank = 1
ORDER BY company, item_code
"""

MASTER_CODES_SQL = """
SELECT DISTINCT
    lpad(CAST(mc_lvl1_code AS STRING), 2, '0') AS mc_lvl1_code,
    lpad(CAST(mc_lvl2_code AS STRING), 2, '0') AS mc_lvl2_code,
    lpad(CAST(mc_lvl3_code AS STRING), 2, '0') AS mc_lvl3_code
FROM dump_pdb_flats
WHERE mc_lvl1_code IS NOT NULL
  AND mc_lvl2_code IS NOT NULL
  AND mc_lvl3_code IS NOT NULL
ORDER BY mc_lvl1_code, mc_lvl2_code, mc_lvl3_code
"""

PDB_SQL = """
SELECT
    company_item_code,
    item_description_cleaned,
    manufacturer_company_name,
    father_name,
    mc_lvl1_code,
    mc_lvl2_code,
    mc_lvl3_code,
    pack,
    feature,
    measure
FROM dump_pdb_flats
WHERE company_item_code IS NOT NULL
  AND trim(company_item_code) <> ''
  AND item_description_cleaned IS NOT NULL
  AND trim(item_description_cleaned) <> ''
"""

DETAIL_COLUMNS = [
    {"field": "first_received_date", "header_name": "First Received Date", "value_type": "date"},
    {"field": "source_file", "header_name": "Product Source File", "value_type": "string"},
    {"field": "search_type", "header_name": "Search Type", "value_type": "string"},
    {"field": "status", "header_name": "Status", "value_type": "string"},
    {"field": "created_date", "header_name": "Created Date", "value_type": "date"},
]


class StatementClient:
    def __init__(self, warehouse_id: str, profile: str, catalog: str, schema: str):
        self.warehouse_id = warehouse_id
        self.profile = profile
        self.catalog = catalog
        self.schema = schema

    def rows(self, statement: str) -> Iterator[dict[str, Any]]:
        response = self._api(
            "post",
            "/api/2.0/sql/statements",
            {
                "warehouse_id": self.warehouse_id,
                "catalog": self.catalog,
                "schema": self.schema,
                "wait_timeout": "50s",
                "format": "CSV",
                "disposition": "EXTERNAL_LINKS",
                "statement": statement,
            },
        )
        statement_id = str(response.get("statement_id") or "")
        while response.get("status", {}).get("state") in {"PENDING", "RUNNING"}:
            time.sleep(2)
            response = self._api("get", f"/api/2.0/sql/statements/{statement_id}")
        state = response.get("status", {}).get("state")
        if state != "SUCCEEDED":
            error = response.get("status", {}).get("error", {})
            raise RuntimeError(f"Statement Databricks {state}: {error.get('message') or error}")

        manifest = response.get("manifest") or {}
        total_chunks = int(manifest.get("total_chunk_count") or 0)
        columns = [column["name"] for column in manifest.get("schema", {}).get("columns", [])]
        if total_chunks <= 0 or not columns:
            return

        first_result = response.get("result") or {}
        for chunk_index in range(total_chunks):
            chunk = first_result if chunk_index == 0 and first_result.get("external_links") else self._api(
                "get",
                f"/api/2.0/sql/statements/{statement_id}/result/chunks/{chunk_index}",
            )
            links = chunk.get("external_links") or chunk.get("result", {}).get("external_links") or []
            if not links:
                raise RuntimeError(f"Link esterno assente per il chunk {chunk_index}")
            yield from self._csv_rows(links[0]["external_link"], columns, chunk_index == 0)

    def _api(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        command = ["databricks", "api", method, path, "--profile", self.profile, "--output", "json"]
        if payload is not None:
            command.extend(["--json", json.dumps(payload)])
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(completed.stdout)

    @staticmethod
    def _csv_rows(url: str, columns: list[str], includes_header: bool) -> Iterator[dict[str, Any]]:
        with requests.get(url, timeout=(30, 900)) as response:
            response.raise_for_status()
            reader = csv.reader(io.StringIO(response.content.decode("utf-8-sig"), newline=""))
            if includes_header:
                header = next(reader, None)
                if header != columns:
                    raise RuntimeError("Header CSV Databricks non coerente con il manifest")
            for values in reader:
                if len(values) != len(columns):
                    raise RuntimeError("Riga CSV Databricks con cardinalita non valida")
                yield {
                    column: None if value == "null" else value
                    for column, value in zip(columns, values, strict=True)
                }


def _proposal(value: Any) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    parsed = json.loads(str(value))
    if not isinstance(parsed, dict):
        raise ValueError("Proposta BS25 non valida")
    return parsed


def _snapshot_payload(
    client: StatementClient, environment: str, snapshot_id: str, created_at: str
) -> dict[str, Any]:
    rows = []
    for source in client.rows(PRODUCTS_SQL):
        details = {key: source.get(key) for key in (
            "first_received_date", "source_file", "search_type", "status", "created_date"
        )}
        rows.append(
            {
                "company": source["company"],
                "item_code": source["item_code"],
                "company_item_code": source["company_item_code"],
                "description": source.get("description"),
                "bs25_status": source.get("bs25_status"),
                "bs25_proposal_1": _proposal(source.get("bs25_proposal_1")),
                "bs25_proposal_2": _proposal(source.get("bs25_proposal_2")),
                "bs25_proposal_3": _proposal(source.get("bs25_proposal_3")),
                "bs25_selected_proposal_rank": source.get("bs25_selected_proposal_rank"),
                "bs25_selected_master_code": source.get("bs25_selected_master_code"),
                "bs25_selection_status": source.get("bs25_selection_status"),
                "details": details,
            }
        )
    if not rows:
        raise RuntimeError("product_to_classify non contiene righe")

    companies = [
        {
            "company": company,
            "full_view_available": True,
            "full_view_message": None,
            "extra_columns": DETAIL_COLUMNS,
        }
        for company in sorted({row["company"] for row in rows})
    ]
    master_codes = []
    for code in client.rows(MASTER_CODES_SQL):
        levels = [str(code[f"mc_lvl{level}_code"]).zfill(2) for level in (1, 2, 3)]
        master_codes.append(
            {
                "master_code": "_".join(levels),
                "components": {
                    "mc_lvl1_code": levels[0],
                    "mc_lvl2_code": levels[1],
                    "mc_lvl3_code": levels[2],
                },
            }
        )
    if not master_codes:
        raise RuntimeError("dump_pdb_flats non contiene Master Code validi")
    return {
        "environment": environment,
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "companies": companies,
        "rows": rows,
        "master_codes": master_codes,
    }


def _publish_remote_files(
    backend_url: str,
    token: str,
    environment: str,
    snapshot_path: Path,
    pdb_path: Path,
) -> dict[str, Any]:
    headers = {"X-Codex-Snapshot-Token": token}
    with snapshot_path.open("rb") as handle:
        response = requests.put(
            f"{backend_url.rstrip('/')}/api/codex/snapshot-file",
            params={"environment": environment},
            headers={**headers, "Content-Type": "application/octet-stream"},
            data=handle,
            timeout=900,
        )
    response.raise_for_status()
    snapshot_receipt = response.json()

    with pdb_path.open("rb") as handle:
        response = requests.put(
            f"{backend_url.rstrip('/')}/api/codex/pdb-snapshot",
            params={"environment": environment},
            headers={**headers, "Content-Type": "application/octet-stream"},
            data=handle,
            timeout=3600,
        )
    response.raise_for_status()
    return {"snapshot": snapshot_receipt, "pdb": response.json()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-id")
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--catalog", default="research_dev")
    parser.add_argument("--schema", default="silver")
    parser.add_argument("--environment", choices=("dev", "prod"), default="dev")
    parser.add_argument("--target-dir", type=Path, default=REPOSITORY_ROOT / "backend" / "data" / "codex")
    parser.add_argument("--backend-url")
    parser.add_argument("--snapshot-token-file", type=Path)
    parser.add_argument(
        "--publish-only",
        action="store_true",
        help="Pubblica i due SQLite correnti senza interrogare nuovamente Databricks",
    )
    args = parser.parse_args()
    if bool(args.backend_url) != bool(args.snapshot_token_file):
        parser.error("--backend-url e --snapshot-token-file devono essere specificati insieme")

    target_dir = args.target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    if args.publish_only:
        if not args.backend_url:
            parser.error("--publish-only richiede --backend-url e --snapshot-token-file")
        snapshot_path = target_dir / f"snapshot-{args.environment}.sqlite3"
        pdb_path = target_dir / f"pdb-{args.environment}.sqlite3"
        if not snapshot_path.is_file() or not pdb_path.is_file():
            raise FileNotFoundError("I due snapshot SQLite correnti non sono disponibili")
        token = args.snapshot_token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError("Token snapshot vuoto")
        receipts = _publish_remote_files(
            args.backend_url, token, args.environment, snapshot_path, pdb_path
        )
        print(json.dumps({"remote": receipts}, ensure_ascii=False))
        return
    if not args.warehouse_id:
        parser.error("--warehouse-id e obbligatorio salvo con --publish-only")

    previous_data_dir = os.environ.get("CODEX_LOCAL_DATA_DIR")
    os.environ["CODEX_LOCAL_DATA_DIR"] = str(target_dir)
    created_at = datetime.now(timezone.utc).isoformat()
    snapshot_id = f"{args.catalog}.{args.schema}-{created_at}"
    client = StatementClient(args.warehouse_id, args.profile, args.catalog, args.schema)
    try:
        payload = _snapshot_payload(client, args.environment, snapshot_id, created_at)
        codex_receipt = publish_snapshot(
            args.environment,
            snapshot_id,
            created_at,
            payload["companies"],
            payload["rows"],
            payload["master_codes"],
        )
        pdb_receipt = publish_pdb_snapshot(
            args.environment,
            f"{args.catalog}.{args.schema}.dump_pdb_flats-{created_at}",
            created_at,
            client.rows(PDB_SQL),
        )
        pdb_path = Path(pdb_receipt["path"])
        remote_receipts = None
        if args.backend_url:
            token = args.snapshot_token_file.read_text(encoding="utf-8").strip()
            if not token:
                raise RuntimeError("Token snapshot vuoto")
            remote_receipts = _publish_remote_files(
                args.backend_url,
                token,
                args.environment,
                Path(codex_receipt["path"]),
                pdb_path,
            )
        print(
            json.dumps(
                {
                    "snapshot": codex_receipt,
                    "pdb": pdb_receipt,
                    "remote": remote_receipts,
                },
                ensure_ascii=False,
            )
        )
    finally:
        if previous_data_dir is None:
            os.environ.pop("CODEX_LOCAL_DATA_DIR", None)
        else:
            os.environ["CODEX_LOCAL_DATA_DIR"] = previous_data_dir


if __name__ == "__main__":
    main()
