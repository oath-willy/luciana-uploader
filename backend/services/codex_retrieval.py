import re
from dataclasses import dataclass
from typing import Any

from services.databricks_statement import (
    DatabricksStatementClient,
    StatementParameter,
)


MAX_LOOKUP_BATCH_SIZE = 20
RETRIEVER_VERSION = "pdb-bm25-current-v1"

_CONTROL_CODE_RE = re.compile(r"(?<![A-Za-z0-9])\d{2}_\d{2}_\d{2}(?![A-Za-z0-9])")
_ESTIMATED_PREFIX_RE = re.compile(r"^[^|\r\n]*estimated[^|\r\n]*\|", re.IGNORECASE)


def normalize_retrieval_description(value: str) -> str:
    """Mirror the runtime normalization without treating the score as confidence."""
    cleaned = str(value)
    if _CONTROL_CODE_RE.search(cleaned):
        cleaned = _ESTIMATED_PREFIX_RE.sub("", cleaned)
    cleaned = _CONTROL_CODE_RE.sub(" ", cleaned)
    return " ".join(
        "".join(character.lower() if character.isalnum() else " " for character in cleaned)
        .split()
    )


@dataclass(frozen=True)
class RetrievalItem:
    item_code: str
    description: str


class PdbBm25Retriever:
    """Batch BM25 retrieval against one frozen-at-query-time current PDB version."""

    def __init__(self, client: DatabricksStatementClient, pdb_table: str):
        self.client = client
        self.pdb_table = pdb_table

    def latest_delta_version(self) -> int:
        rows = self.client.execute(
            f"DESCRIBE HISTORY {self.pdb_table} LIMIT 1",
            timeout_seconds=180,
        )
        if not rows or rows[0].get("version") is None:
            raise RuntimeError("Versione Delta del PDB non disponibile")
        return int(rows[0]["version"])

    def retrieve(
        self,
        items: list[RetrievalItem],
        delta_version: int,
    ) -> dict[str, list[dict[str, Any]]]:
        if not items:
            return {}
        if len(items) > MAX_LOOKUP_BATCH_SIZE:
            raise ValueError(
                f"Seleziona al massimo {MAX_LOOKUP_BATCH_SIZE} record per analisi"
            )
        if delta_version < 0:
            raise ValueError("Versione Delta PDB non valida")

        parameters: list[StatementParameter] = []
        value_rows = []
        for index, item in enumerate(items):
            normalized = normalize_retrieval_description(item.description)
            if not normalized:
                raise ValueError(f"Descrizione vuota per item {item.item_code}")
            value_rows.append(
                f"(:item_code_{index}, :description_{index}, :normalized_{index})"
            )
            parameters.extend(
                [
                    StatementParameter(f"item_code_{index}", item.item_code),
                    StatementParameter(f"description_{index}", item.description),
                    StatementParameter(f"normalized_{index}", normalized),
                ]
            )

        sql = self._retrieval_sql(
            values_sql=",\n".join(value_rows),
            delta_version=delta_version,
        )
        rows = self.client.execute(sql, parameters, timeout_seconds=600)
        proposals: dict[str, list[dict[str, Any]]] = {
            item.item_code: [] for item in items
        }
        for row in rows:
            item_code = str(row.pop("query_item_code"))
            row["identity_rank"] = int(row["identity_rank"])
            row["identity_score"] = float(row["identity_score"])
            row["exact_match"] = bool(row["exact_match"])
            proposals.setdefault(item_code, []).append(row)

        for item in items:
            item_proposals = proposals.get(item.item_code, [])
            if len(item_proposals) != 3:
                raise RuntimeError(
                    f"Il retriever ha restituito {len(item_proposals)} proposte "
                    f"per {item.item_code}, attese 3"
                )
        return proposals

    def _retrieval_sql(self, values_sql: str, delta_version: int) -> str:
        # The version is an integer obtained from DESCRIBE HISTORY, never user input.
        return f"""
            WITH queries AS (
                SELECT *
                FROM VALUES
                    {values_sql}
                AS q(item_code, raw_description, query_norm)
            ),
            query_docs AS (
                SELECT
                    item_code,
                    raw_description,
                    query_norm,
                    CASE
                        WHEN size(filter(
                            split(query_norm, ' '),
                            token -> length(token) >= 2
                        )) > 0
                        THEN array_distinct(filter(
                            split(query_norm, ' '),
                            token -> length(token) >= 2
                        ))
                        ELSE array('__bs25_no_matching_token__')
                    END AS query_tokens
                FROM queries
            ),
            pdb_normalized AS (
                SELECT
                    company_item_code AS pdb_ref,
                    item_description_cleaned AS pdb_description,
                    manufacturer_company_name AS manufacturer,
                    father_name,
                    pack,
                    feature,
                    measure,
                    mc_lvl1_code,
                    mc_lvl2_code,
                    mc_lvl3_code,
                    trim(regexp_replace(
                        lower(regexp_replace(
                            COALESCE(item_description_cleaned, ''),
                            r'(?<![\\p{{L}}\\p{{N}}])[0-9]{{2}}_[0-9]{{2}}_[0-9]{{2}}(?![\\p{{L}}\\p{{N}}])',
                            ' '
                        )),
                        r'[^\\p{{L}}\\p{{N}}]+',
                        ' '
                    )) AS pdb_norm
                FROM {self.pdb_table} VERSION AS OF {int(delta_version)}
                WHERE company_item_code IS NOT NULL
                  AND TRIM(company_item_code) <> ''
            ),
            pdb_docs AS (
                SELECT
                    *,
                    filter(split(pdb_norm, ' '), token -> length(token) >= 2)
                        AS pdb_tokens
                FROM pdb_normalized
            ),
            pdb_stats AS (
                SELECT
                    COUNT(*) AS document_count,
                    AVG(size(pdb_tokens)) AS average_document_length
                FROM pdb_docs
            ),
            query_terms AS (
                SELECT
                    q.item_code,
                    q.query_norm,
                    token
                FROM query_docs AS q
                LATERAL VIEW explode(q.query_tokens) exploded AS token
            ),
            term_stats AS (
                SELECT
                    qt.item_code,
                    qt.token,
                    COUNT_IF(array_contains(p.pdb_tokens, qt.token))
                        AS document_frequency
                FROM query_terms AS qt
                CROSS JOIN pdb_docs AS p
                GROUP BY qt.item_code, qt.token
            ),
            seed_terms AS (
                SELECT item_code, token
                FROM (
                    SELECT
                        item_code,
                        token,
                        ROW_NUMBER() OVER (
                            PARTITION BY item_code
                            ORDER BY document_frequency, length(token) DESC, token
                        ) AS seed_rank
                    FROM term_stats
                    WHERE document_frequency > 0
                )
                WHERE seed_rank <= 3
            ),
            candidate_keys AS (
                SELECT DISTINCT
                    seed.item_code,
                    p.pdb_ref
                FROM seed_terms AS seed
                INNER JOIN pdb_docs AS p
                    ON array_contains(p.pdb_tokens, seed.token)
            ),
            fallback_pdb AS (
                SELECT pdb_ref
                FROM pdb_docs
                ORDER BY pdb_ref
                LIMIT 3
            ),
            candidate_pool AS (
                SELECT item_code, pdb_ref FROM candidate_keys
                UNION
                SELECT q.item_code, p.pdb_ref
                FROM query_docs AS q
                CROSS JOIN fallback_pdb AS p
            ),
            candidate_docs AS (
                SELECT pool.item_code, p.*
                FROM candidate_pool AS pool
                INNER JOIN pdb_docs AS p ON p.pdb_ref = pool.pdb_ref
            ),
            scored_terms AS (
                SELECT
                    candidate.item_code,
                    candidate.pdb_ref,
                    candidate.pdb_description,
                    candidate.manufacturer,
                    candidate.father_name,
                    candidate.pack,
                    candidate.feature,
                    candidate.measure,
                    candidate.mc_lvl1_code,
                    candidate.mc_lvl2_code,
                    candidate.mc_lvl3_code,
                    candidate.pdb_norm,
                    candidate.pdb_tokens,
                    query.query_norm,
                    term.token,
                    size(filter(
                        candidate.pdb_tokens,
                        candidate_token -> candidate_token = term.token
                    )) AS term_frequency,
                    log(
                        1 + (
                            stats.document_count -
                            COALESCE(term_stats.document_frequency, 0) + 0.5
                        ) / (
                            COALESCE(term_stats.document_frequency, 0) + 0.5
                        )
                    ) AS inverse_document_frequency,
                    size(candidate.pdb_tokens) AS document_length,
                    stats.average_document_length
                FROM candidate_docs AS candidate
                INNER JOIN query_docs AS query
                    ON query.item_code = candidate.item_code
                INNER JOIN query_terms AS term
                    ON term.item_code = candidate.item_code
                LEFT JOIN term_stats
                    ON term_stats.item_code = term.item_code
                   AND term_stats.token = term.token
                CROSS JOIN pdb_stats AS stats
            ),
            candidate_scores AS (
                SELECT
                    item_code,
                    pdb_ref,
                    FIRST(pdb_description) AS pdb_description,
                    FIRST(manufacturer) AS manufacturer,
                    FIRST(father_name) AS father_name,
                    FIRST(pack) AS pack,
                    FIRST(feature) AS feature,
                    FIRST(measure) AS measure,
                    FIRST(mc_lvl1_code) AS mc_lvl1_code,
                    FIRST(mc_lvl2_code) AS mc_lvl2_code,
                    FIRST(mc_lvl3_code) AS mc_lvl3_code,
                    FIRST(pdb_norm) AS pdb_norm,
                    FIRST(query_norm) AS query_norm,
                    SUM(
                        CASE WHEN term_frequency > 0 THEN
                            inverse_document_frequency *
                            (term_frequency * (1.2 + 1)) /
                            (
                                term_frequency + 1.2 *
                                (
                                    1 - 0.75 + 0.75 *
                                    document_length / average_document_length
                                )
                            )
                        ELSE 0 END
                    ) AS raw_bm25,
                    SUM(inverse_document_frequency) * (1.2 + 1)
                        AS maximum_bm25
                FROM scored_terms
                GROUP BY item_code, pdb_ref
            ),
            scored AS (
                SELECT
                    *,
                    pdb_norm = query_norm AS exact_match,
                    (
                        CAST(pdb_norm = query_norm AS INT) +
                        LEAST(raw_bm25 / NULLIF(maximum_bm25, 0), 1)
                    ) / 2 AS identity_score
                FROM candidate_scores
            ),
            ranked AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY item_code
                        ORDER BY
                            identity_score DESC,
                            exact_match DESC,
                            pdb_ref
                    ) AS identity_rank
                FROM scored
            )
            SELECT
                item_code AS query_item_code,
                identity_rank,
                identity_score,
                exact_match,
                pdb_ref,
                pdb_description,
                manufacturer,
                father_name,
                pack,
                feature,
                measure,
                CASE
                    WHEN mc_lvl1_code IS NOT NULL
                     AND mc_lvl2_code IS NOT NULL
                     AND mc_lvl3_code IS NOT NULL
                    THEN concat(
                        lpad(CAST(mc_lvl1_code AS STRING), 2, '0'), '_',
                        lpad(CAST(mc_lvl2_code AS STRING), 2, '0'), '_',
                        lpad(CAST(mc_lvl3_code AS STRING), 2, '0')
                    )
                    ELSE NULL
                END AS master_code
            FROM ranked
            WHERE identity_rank <= 3
            ORDER BY query_item_code, identity_rank
        """
