import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from services.databricks_statement import (
    DatabricksStatementClient,
    StatementParameter,
)
from services.codex_retrieval import (
    RETRIEVER_VERSION,
    PdbBm25Retriever,
    RetrievalItem,
)


CodexEnvironmentName = Literal["dev", "prod"]
CodexView = Literal["light", "full"]
MAX_EXTRA_COLUMNS = 12
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DEV_HOST = "https://adb-7405615217138564.4.azuredatabricks.net"
DEV_WAREHOUSE_ID = "20d27f798c5ecb0a"
DEV_WORKSPACE_RESOURCE_ID = (
    "/subscriptions/546da66c-dbcc-4d4f-9a5b-abf58c1368ef/"
    "resourceGroups/rg-keystone-research-dev/providers/"
    "Microsoft.Databricks/workspaces/dbw-keystone-research-dev"
)


@dataclass(frozen=True)
class EnvironmentSettings:
    name: CodexEnvironmentName
    label: str
    host: str
    warehouse_id: str
    workspace_resource_id: str
    catalog: str
    mapping_file: Path
    available: bool
    unavailable_reason: str | None = None

    @property
    def dataset_name(self) -> str:
        return f"{self.catalog}.silver.product_to_classify"


@dataclass(frozen=True)
class ExtraColumn:
    source_field: str
    field: str
    header_name: str
    value_type: str = "string"

    def as_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "header_name": self.header_name,
            "value_type": self.value_type,
        }


@dataclass(frozen=True)
class CompanyMapping:
    company: str
    mapping_key: str
    landing_table: str
    extra_columns: tuple[ExtraColumn, ...]


def environment_settings(name: CodexEnvironmentName) -> EnvironmentSettings:
    config_dir = Path(__file__).resolve().parents[1] / "config" / "codex"

    if name == "dev":
        return EnvironmentSettings(
            name="dev",
            label="Dev",
            host=os.getenv("CODEX_DATABRICKS_DEV_HOST", DEV_HOST).strip(),
            warehouse_id=os.getenv(
                "CODEX_DATABRICKS_DEV_WAREHOUSE_ID", DEV_WAREHOUSE_ID
            ).strip(),
            workspace_resource_id=os.getenv(
                "CODEX_DATABRICKS_DEV_WORKSPACE_RESOURCE_ID",
                DEV_WORKSPACE_RESOURCE_ID,
            ).strip(),
            catalog=os.getenv("CODEX_DATABRICKS_DEV_CATALOG", "research_dev").strip(),
            mapping_file=config_dir / "pdb_field_mapping.dev.json",
            available=True,
        )

    host = os.getenv("CODEX_DATABRICKS_PROD_HOST", "").strip()
    warehouse_id = os.getenv("CODEX_DATABRICKS_PROD_WAREHOUSE_ID", "").strip()
    workspace_resource_id = os.getenv(
        "CODEX_DATABRICKS_PROD_WORKSPACE_RESOURCE_ID", ""
    ).strip()
    mapping_file = config_dir / "pdb_field_mapping.prod.json"
    available = bool(
        host and warehouse_id and workspace_resource_id and mapping_file.exists()
    )

    return EnvironmentSettings(
        name="prod",
        label="Prod",
        host=host,
        warehouse_id=warehouse_id,
        workspace_resource_id=workspace_resource_id,
        catalog=os.getenv("CODEX_DATABRICKS_PROD_CATALOG", "research_prod").strip(),
        mapping_file=mapping_file,
        available=available,
        unavailable_reason=None
        if available
        else "Workspace Databricks e mapping GitHub main non ancora disponibili",
    )


def environment_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "value": settings.name,
            "label": settings.label,
            "available": settings.available,
            "message": settings.unavailable_reason,
        }
        for settings in (environment_settings("dev"), environment_settings("prod"))
    ]


@lru_cache(maxsize=2)
def load_mapping(environment: CodexEnvironmentName) -> tuple[dict, dict[str, CompanyMapping]]:
    settings = environment_settings(environment)
    if not settings.available:
        raise ValueError(settings.unavailable_reason or "Ambiente non disponibile")

    with settings.mapping_file.open(encoding="utf-8") as mapping_file:
        raw_mapping = json.load(mapping_file)

    companies: dict[str, CompanyMapping] = {}
    for company, item in raw_mapping.get("companies", {}).items():
        landing_table = _identifier(item["landing_table"])
        fields = tuple(
            ExtraColumn(
                source_field=_identifier(source_field),
                field=f"landing_{source_field}",
                header_name=_header_name(source_field),
            )
            for source_field in item.get("extra_fields", [])[:MAX_EXTRA_COLUMNS]
        )
        companies[company.upper()] = CompanyMapping(
            company=company.upper(),
            mapping_key=item["mapping_key"],
            landing_table=landing_table,
            extra_columns=fields,
        )

    return raw_mapping.get("source", {}), companies


class CodexRepository:
    def __init__(self, environment: CodexEnvironmentName):
        self.settings = environment_settings(environment)
        if not self.settings.available:
            raise ValueError(
                self.settings.unavailable_reason or "Ambiente Databricks non disponibile"
            )
        _identifier(self.settings.catalog)
        self.mapping_source, self.company_mappings = load_mapping(environment)
        self.client = DatabricksStatementClient(
            host=self.settings.host,
            warehouse_id=self.settings.warehouse_id,
            catalog=self.settings.catalog,
            schema="silver",
        )
        self.bs25_retriever = PdbBm25Retriever(self.client, self._pdb_table)

    def companies(self) -> list[dict[str, Any]]:
        rows = self.client.execute(
            f"""
            SELECT DISTINCT UPPER(TRIM(company)) AS company
            FROM {self._product_table}
            WHERE company IS NOT NULL AND TRIM(company) <> ''
            ORDER BY company
            """
        )
        return [
            {
                "value": row["company"],
                "label": row["company"],
                "full_view_available": row["company"] in self.company_mappings,
                "full_view_message": None
                if row["company"] in self.company_mappings
                else "Nessun mapping di campi FULL presente nel branch configurato",
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
        mapping = self.company_mappings.get(company.upper()) if view == "full" else None
        extra_columns = list(mapping.extra_columns) if mapping else []
        ctes = [self._selected_products_cte(), self._bs25_cte()]

        if mapping:
            ctes.extend(self._landing_ctes(mapping))
            extra_select = ",\n".join(
                f"lr.{_quote(column.source_field)} AS {_quote(column.field)}"
                for column in extra_columns
            )
            landing_join_clause = """
                LEFT JOIN landing_ranked AS lr
                    ON lr._landing_key = UPPER(TRIM(p.company_item_code))
                   AND lr._landing_rank = 1
            """
        else:
            extra_select = ""
            landing_join_clause = ""

        select_columns = [
            "p.company",
            "p.item_code",
            "p.company_item_code",
            "p.description",
            "bs25.lookup_status AS bs25_status",
            "bs25.proposal_1 AS bs25_proposal_1",
            "bs25.proposal_2 AS bs25_proposal_2",
            "bs25.proposal_3 AS bs25_proposal_3",
            "bs25.selected_proposal_rank AS bs25_selected_proposal_rank",
            "bs25.selected_pdb_ref AS bs25_selected_pdb_ref",
            "bs25.selected_master_code AS bs25_selected_master_code",
            "bs25.pending_proposal_rank AS bs25_pending_proposal_rank",
            "bs25.selection_status AS bs25_selection_status",
            "bs25.selection_request_id AS bs25_selection_request_id",
            "bs25.selection_error_message AS bs25_selection_error_message",
        ]
        if extra_select:
            select_columns.append(extra_select)

        ctes.append(
            "enriched AS (\n"
            f"SELECT {', '.join(select_columns)}\n"
            "FROM selected_products AS p\n"
            f"{landing_join_clause}\n"
            "LEFT JOIN bs25_latest AS bs25\n"
            "  ON UPPER(TRIM(bs25.company)) = UPPER(TRIM(p.company))\n"
            " AND TRIM(bs25.item_code) = TRIM(p.item_code)\n"
            ")"
        )

        allowed_fields = {
            "company_item_code": "company_item_code",
            "description": "description",
            **{column.field: column.field for column in extra_columns},
        }
        where_clause, filter_parameters = self._filters(
            search, filters, allowed_fields
        )
        ctes.append(f"filtered AS (SELECT * FROM enriched {where_clause})")

        output_columns = [
            "company",
            "item_code",
            "company_item_code",
            "description",
            "bs25_status",
            "bs25_proposal_1",
            "bs25_proposal_2",
            "bs25_proposal_3",
            "bs25_selected_proposal_rank",
            "bs25_selected_pdb_ref",
            "bs25_selected_master_code",
            "bs25_pending_proposal_rank",
            "bs25_selection_status",
            "bs25_selection_request_id",
            "bs25_selection_error_message",
        ]
        output_columns.extend(column.field for column in extra_columns)
        output_sql = ", ".join(_quote(column) for column in output_columns)

        sql = f"""
            WITH {', '.join(ctes)}
            SELECT
                company_item_code AS id,
                {output_sql},
                COUNT(*) OVER () AS _total_count
            FROM filtered
            ORDER BY company_item_code
            LIMIT :row_limit OFFSET :row_offset
        """
        parameters = [
            StatementParameter("company", company),
            *filter_parameters,
            StatementParameter("row_limit", page_size, "INT"),
            StatementParameter("row_offset", page * page_size, "INT"),
        ]
        rows = self.client.execute(sql, parameters)
        total = int(rows[0].pop("_total_count", 0)) if rows else 0

        for row in rows:
            row.pop("_total_count", None)
            row["fuzzy_lookup_status"] = None
            row["ai_lookup_status"] = None
            for field in (
                "bs25_proposal_1",
                "bs25_proposal_2",
                "bs25_proposal_3",
            ):
                row[field] = json.loads(row[field]) if row.get(field) else None

        return {
            "rows": rows,
            "total": total,
            "extra_columns": [column.as_dict() for column in extra_columns],
        }

    def submit_bs25_lookup(
        self,
        company: str,
        item_codes: list[str],
        requested_by: str,
    ) -> dict[str, Any]:
        source_rows = self._bs25_source_rows(company, item_codes)
        source_by_item = {str(row["item_code"]): row for row in source_rows}
        missing = [item_code for item_code in item_codes if item_code not in source_by_item]
        if missing:
            raise ValueError(f"Record CODEX non trovati: {', '.join(missing)}")

        existing = self._existing_bs25_items(company, item_codes)
        accepted = [item_code for item_code in item_codes if item_code not in existing]
        if accepted:
            self._insert_bs25_items(
                company=company,
                source_rows=[source_by_item[item_code] for item_code in accepted],
                requested_by=requested_by,
            )

        return {
            "accepted_item_codes": accepted,
            "locked_item_codes": [
                item_code for item_code in item_codes if item_code in existing
            ],
        }

    def run_bs25_lookup(self, company: str, item_codes: list[str]) -> None:
        source_rows = self._bs25_source_rows(company, item_codes)
        retrieval_items = [
            RetrievalItem(
                item_code=str(row["item_code"]),
                description=str(row["description"]),
            )
            for row in source_rows
        ]
        try:
            delta_version = self.bs25_retriever.latest_delta_version()
            proposals = self.bs25_retriever.retrieve(retrieval_items, delta_version)
            self._complete_bs25_items(company, proposals, delta_version)
        except Exception as exc:
            self._fail_bs25_items(company, item_codes, str(exc))
            raise

    def queue_bs25_selection(
        self,
        company: str,
        item_code: str,
        proposal_rank: int,
        selection_request_id: str,
    ) -> None:
        self._mark_bs25_selection_saving(
            company,
            item_code,
            proposal_rank,
            selection_request_id,
        )

    def complete_bs25_selection(
        self,
        company: str,
        item_code: str,
        proposal_rank: int,
        selected_by: str,
        selection_request_id: str,
    ) -> dict[str, Any]:
        try:
            proposal_column = f"proposal_{proposal_rank}"
            rows = self.client.execute(
                f"""
                SELECT
                    {proposal_column} AS proposal,
                    selection_status,
                    selection_request_id
                FROM {self._bs25_table}
                WHERE UPPER(TRIM(company)) = UPPER(TRIM(:company))
                  AND TRIM(item_code) = TRIM(:item_code)
                  AND lookup_status = 'completed'
                LIMIT 1
                """,
                [
                    StatementParameter("company", company),
                    StatementParameter("item_code", item_code),
                ],
            )
            if not rows or not rows[0].get("proposal"):
                raise ValueError("Proposta BS25 non disponibile")

            proposal = json.loads(rows[0]["proposal"])
            if rows[0].get("selection_request_id") != selection_request_id:
                return proposal
            if rows[0].get("selection_status") == "completed":
                return proposal
            self.client.execute(
                f"""
                UPDATE {self._bs25_table}
                SET selected_proposal_rank = :proposal_rank,
                    selected_pdb_ref = :pdb_ref,
                    selected_master_code = :master_code,
                    pending_proposal_rank = NULL,
                    selection_status = 'completed',
                    selection_error_message = NULL,
                    selected_by = :selected_by,
                    selected_at = current_timestamp()
                WHERE UPPER(TRIM(company)) = UPPER(TRIM(:company))
                  AND TRIM(item_code) = TRIM(:item_code)
                  AND lookup_status = 'completed'
                  AND selection_request_id = :selection_request_id
                """,
                [
                    StatementParameter("proposal_rank", proposal_rank, "INT"),
                    StatementParameter("pdb_ref", proposal.get("pdb_ref", "")),
                    StatementParameter(
                        "master_code", proposal.get("master_code") or ""
                    ),
                    StatementParameter("selected_by", selected_by),
                    StatementParameter("company", company),
                    StatementParameter("item_code", item_code),
                    StatementParameter(
                        "selection_request_id", selection_request_id
                    ),
                ],
            )
            return proposal
        except Exception as exc:
            self._fail_bs25_selection(
                company,
                item_code,
                selection_request_id,
                str(exc),
            )
            raise

    def _mark_bs25_selection_saving(
        self,
        company: str,
        item_code: str,
        proposal_rank: int,
        selection_request_id: str,
    ) -> None:
        self.client.execute(
            f"""
            UPDATE {self._bs25_table}
            SET pending_proposal_rank = :proposal_rank,
                selection_status = 'saving',
                selection_request_id = :selection_request_id,
                selection_error_message = NULL,
                selection_requested_at = current_timestamp()
            WHERE UPPER(TRIM(company)) = UPPER(TRIM(:company))
              AND TRIM(item_code) = TRIM(:item_code)
              AND lookup_status = 'completed'
              AND NOT (
                  COALESCE(selection_request_id, '') = :selection_request_id
                  AND selection_status IN ('saving', 'completed')
              )
            """,
            [
                StatementParameter("proposal_rank", proposal_rank, "INT"),
                StatementParameter("selection_request_id", selection_request_id),
                StatementParameter("company", company),
                StatementParameter("item_code", item_code),
            ],
        )

    def _fail_bs25_selection(
        self,
        company: str,
        item_code: str,
        selection_request_id: str,
        error_message: str,
    ) -> None:
        self.client.execute(
            f"""
            UPDATE {self._bs25_table}
            SET pending_proposal_rank = NULL,
                selection_status = 'failed',
                selection_error_message = :error_message
            WHERE UPPER(TRIM(company)) = UPPER(TRIM(:company))
              AND TRIM(item_code) = TRIM(:item_code)
              AND selection_request_id = :selection_request_id
            """,
            [
                StatementParameter("error_message", error_message[:2000]),
                StatementParameter("company", company),
                StatementParameter("item_code", item_code),
                StatementParameter("selection_request_id", selection_request_id),
            ],
        )

    def _bs25_source_rows(
        self,
        company: str,
        item_codes: list[str],
    ) -> list[dict[str, Any]]:
        if not item_codes:
            return []
        item_conditions = []
        parameters = [StatementParameter("company", company)]
        for index, item_code in enumerate(item_codes):
            parameter_name = f"bs25_item_code_{index}"
            item_conditions.append(f"TRIM(item_code) = TRIM(:{parameter_name})")
            parameters.append(StatementParameter(parameter_name, item_code))

        return self.client.execute(
            f"""
            SELECT
                item_code,
                CONCAT(TRIM(company), '|', TRIM(item_code)) AS company_item_code,
                description
            FROM {self._product_table}
            WHERE UPPER(TRIM(company)) = UPPER(TRIM(:company))
              AND ({' OR '.join(item_conditions)})
            """,
            parameters,
        )

    def _existing_bs25_items(
        self,
        company: str,
        item_codes: list[str],
    ) -> set[str]:
        if not item_codes:
            return set()
        item_conditions = []
        parameters = [StatementParameter("company", company)]
        for index, item_code in enumerate(item_codes):
            parameter_name = f"existing_item_code_{index}"
            item_conditions.append(f"TRIM(item_code) = TRIM(:{parameter_name})")
            parameters.append(StatementParameter(parameter_name, item_code))
        rows = self.client.execute(
            f"""
            SELECT item_code
            FROM {self._bs25_table}
            WHERE UPPER(TRIM(company)) = UPPER(TRIM(:company))
              AND ({' OR '.join(item_conditions)})
            """,
            parameters,
        )
        return {str(row["item_code"]) for row in rows}

    def _insert_bs25_items(
        self,
        company: str,
        source_rows: list[dict[str, Any]],
        requested_by: str,
    ) -> None:
        value_rows = []
        parameters: list[StatementParameter] = []
        for index, row in enumerate(source_rows):
            value_rows.append(
                "(" + ", ".join(
                    (
                        f":company_{index}",
                        f":item_code_{index}",
                        f":company_item_code_{index}",
                        f":description_{index}",
                    )
                ) + ")"
            )
            parameters.extend(
                [
                    StatementParameter(f"company_{index}", company),
                    StatementParameter(f"item_code_{index}", row["item_code"]),
                    StatementParameter(
                        f"company_item_code_{index}", row["company_item_code"]
                    ),
                    StatementParameter(f"description_{index}", row["description"]),
                ]
            )
        parameters.append(StatementParameter("requested_by", requested_by))

        self.client.execute(
            f"""
            MERGE INTO {self._bs25_table} AS target
            USING (
                SELECT * FROM VALUES
                    {', '.join(value_rows)}
                AS source(company, item_code, company_item_code, description)
            ) AS source
            ON UPPER(TRIM(target.company)) = UPPER(TRIM(source.company))
               AND TRIM(target.item_code) = TRIM(source.item_code)
            WHEN NOT MATCHED THEN INSERT (
                company,
                item_code,
                company_item_code,
                description,
                lookup_status,
                retriever_version,
                requested_by,
                requested_at
            ) VALUES (
                source.company,
                source.item_code,
                source.company_item_code,
                source.description,
                'analyzing',
                '{RETRIEVER_VERSION}',
                :requested_by,
                current_timestamp()
            )
            """,
            parameters,
        )

    def _complete_bs25_items(
        self,
        company: str,
        proposals: dict[str, list[dict[str, Any]]],
        delta_version: int,
    ) -> None:
        value_rows = []
        parameters: list[StatementParameter] = []
        for index, (item_code, item_proposals) in enumerate(proposals.items()):
            value_rows.append(
                f"(:item_code_{index}, :proposal_1_{index}, "
                f":proposal_2_{index}, :proposal_3_{index})"
            )
            parameters.append(StatementParameter(f"item_code_{index}", item_code))
            for rank, proposal in enumerate(item_proposals, start=1):
                parameters.append(
                    StatementParameter(
                        f"proposal_{rank}_{index}",
                        json.dumps(
                            proposal,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                )
        parameters.extend(
            [
                StatementParameter("company", company),
                StatementParameter("pdb_delta_version", delta_version, "LONG"),
            ]
        )
        self.client.execute(
            f"""
            MERGE INTO {self._bs25_table} AS target
            USING (
                SELECT * FROM VALUES
                    {', '.join(value_rows)}
                AS source(item_code, proposal_1, proposal_2, proposal_3)
            ) AS source
            ON UPPER(TRIM(target.company)) = UPPER(TRIM(:company))
               AND TRIM(target.item_code) = TRIM(source.item_code)
            WHEN MATCHED THEN UPDATE SET
                target.lookup_status = 'completed',
                target.pdb_delta_version = :pdb_delta_version,
                target.proposal_1 = source.proposal_1,
                target.proposal_2 = source.proposal_2,
                target.proposal_3 = source.proposal_3,
                target.completed_at = current_timestamp(),
                target.error_message = NULL
            """,
            parameters,
        )

    def _fail_bs25_items(
        self,
        company: str,
        item_codes: list[str],
        error_message: str,
    ) -> None:
        if not item_codes:
            return
        item_conditions = []
        parameters = [
            StatementParameter("company", company),
            StatementParameter("error_message", error_message[:2000]),
        ]
        for index, item_code in enumerate(item_codes):
            parameter_name = f"failed_item_code_{index}"
            item_conditions.append(f"TRIM(item_code) = TRIM(:{parameter_name})")
            parameters.append(StatementParameter(parameter_name, item_code))
        self.client.execute(
            f"""
            UPDATE {self._bs25_table}
            SET lookup_status = 'failed',
                error_message = :error_message,
                completed_at = current_timestamp()
            WHERE UPPER(TRIM(company)) = UPPER(TRIM(:company))
              AND ({' OR '.join(item_conditions)})
            """,
            parameters,
        )

    def detail(self, company: str, item_code: str) -> dict[str, Any] | None:
        mapping = self.company_mappings.get(company.upper())
        extra_columns = list(mapping.extra_columns) if mapping else []
        ctes = [self._selected_products_cte(item_code=True)]

        if mapping:
            ctes.extend(self._landing_ctes(mapping))
            extra_select = ",\n".join(
                f"lr.{_quote(column.source_field)} AS {_quote(column.field)}"
                for column in extra_columns
            )
            join_clause = """
                LEFT JOIN landing_ranked AS lr
                    ON lr._landing_key = UPPER(TRIM(p.company_item_code))
                   AND lr._landing_rank = 1
            """
        else:
            extra_select = ""
            join_clause = ""

        sql = f"""
            WITH {', '.join(ctes)}
            SELECT
                p.*
                {',' if extra_select else ''}
                {extra_select}
            FROM selected_products AS p
            {join_clause}
            LIMIT 1
        """
        rows = self.client.execute(
            sql,
            [
                StatementParameter("company", company),
                StatementParameter("item_code", item_code),
            ],
        )
        if not rows:
            return None

        return {
            "record": rows[0],
            "extra_columns": [column.as_dict() for column in extra_columns],
        }

    @property
    def _product_table(self) -> str:
        return (
            f"{_quote(self.settings.catalog)}.{_quote('silver')}."
            f"{_quote('product_to_classify')}"
        )

    @property
    def _bs25_table(self) -> str:
        return (
            f"{_quote(self.settings.catalog)}.{_quote('silver')}."
            f"{_quote('codex_bs25_lookup')}"
        )

    @property
    def _pdb_table(self) -> str:
        return (
            f"{_quote(self.settings.catalog)}.{_quote('silver')}."
            f"{_quote('dump_pdb_flats')}"
        )

    def _bs25_cte(self) -> str:
        return f"""
            bs25_latest AS (
                SELECT
                    company,
                    item_code,
                    lookup_status,
                    proposal_1,
                    proposal_2,
                    proposal_3,
                    selected_proposal_rank,
                    selected_pdb_ref,
                    selected_master_code,
                    pending_proposal_rank,
                    selection_status,
                    selection_request_id,
                    selection_error_message
                FROM {self._bs25_table}
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY UPPER(TRIM(company)), TRIM(item_code)
                    ORDER BY requested_at DESC
                ) = 1
            )
        """

    @property
    def _bronze_schema(self) -> str:
        return f"{_quote(self.settings.catalog)}.{_quote('bronze')}"

    def _selected_products_cte(self, item_code: bool = False) -> str:
        item_filter = " AND TRIM(item_code) = TRIM(:item_code)" if item_code else ""
        return f"""
            selected_products AS (
                SELECT
                    company,
                    item_code,
                    CONCAT(TRIM(company), '|', TRIM(item_code)) AS company_item_code,
                    description,
                    first_received_date,
                    source_file,
                    search_type,
                    status,
                    created_date
                FROM {self._product_table}
                WHERE UPPER(TRIM(company)) = UPPER(TRIM(:company))
                {item_filter}
            )
        """

    def _landing_ctes(self, mapping: CompanyMapping) -> list[str]:
        landing_table = f"{self._bronze_schema}.{_quote(mapping.landing_table)}"
        source_fields = ", ".join(
            f"l.{_quote(column.source_field)}" for column in mapping.extra_columns
        )
        if source_fields:
            source_fields = f", {source_fields}"

        return [
            "selected_keys AS ("
            "SELECT DISTINCT UPPER(TRIM(company_item_code)) AS _landing_key "
            "FROM selected_products)",
            f"""
            landing_ranked AS (
                SELECT
                    UPPER(TRIM(l.company_item_code)) AS _landing_key
                    {source_fields},
                    ROW_NUMBER() OVER (
                        PARTITION BY UPPER(TRIM(l.company_item_code))
                        ORDER BY l.date DESC NULLS LAST, l.file_name DESC NULLS LAST
                    ) AS _landing_rank
                FROM {landing_table} AS l
                INNER JOIN selected_keys AS k
                    ON k._landing_key = UPPER(TRIM(l.company_item_code))
            )
            """,
        ]

    def _filters(
        self,
        search: str,
        filters: dict[str, Any],
        allowed_fields: dict[str, str],
    ) -> tuple[str, list[StatementParameter]]:
        clauses: list[str] = []
        parameters: list[StatementParameter] = []

        if search.strip():
            searchable = [
                f"LOWER(COALESCE(CAST({_quote(field)} AS STRING), '')) "
                "LIKE :global_search ESCAPE '\\\\'"
                for field in allowed_fields.values()
            ]
            clauses.append(f"({' OR '.join(searchable)})")
            parameters.append(
                StatementParameter("global_search", _like_value(search))
            )

        for index, (field, raw_value) in enumerate(filters.items()):
            value = str(raw_value).strip()
            if not value:
                continue
            if field not in allowed_fields:
                raise ValueError(f"Filtro non supportato: {field}")
            parameter_name = f"column_filter_{index}"
            clauses.append(
                f"LOWER(COALESCE(CAST({_quote(allowed_fields[field])} AS STRING), '')) "
                f"LIKE :{parameter_name} ESCAPE '\\\\'"
            )
            parameters.append(
                StatementParameter(parameter_name, _like_value(value))
            )

        return (f"WHERE {' AND '.join(clauses)}" if clauses else "", parameters)


def _identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Identificatore Databricks non valido: {value}")
    return value


def _quote(value: str) -> str:
    return f"`{_identifier(value)}`"


def _like_value(value: str) -> str:
    escaped = value.strip().lower().replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _header_name(field: str) -> str:
    labels = {
        "item_description": "Landing Item Description",
        "item_code": "Landing Item Code",
        "file_name": "Source File",
    }
    return labels.get(field, field.replace("_", " ").title())
