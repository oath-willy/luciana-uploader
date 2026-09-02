-- Dev persistence for the CODEX BS25 candidate-retrieval workflow.
-- Use the corresponding catalog name when promoting the feature to production.
CREATE TABLE IF NOT EXISTS research_dev.silver.codex_bs25_lookup (
    company STRING,
    item_code STRING,
    company_item_code STRING,
    description STRING,
    lookup_status STRING,
    retriever_version STRING,
    pdb_delta_version BIGINT,
    proposal_1 STRING,
    proposal_2 STRING,
    proposal_3 STRING,
    selected_proposal_rank INT,
    selected_pdb_ref STRING,
    selected_master_code STRING,
    pending_proposal_rank INT,
    selection_status STRING,
    selection_request_id STRING,
    selection_error_message STRING,
    selection_requested_at TIMESTAMP,
    requested_by STRING,
    requested_at TIMESTAMP,
    completed_at TIMESTAMP,
    selected_by STRING,
    selected_at TIMESTAMP,
    error_message STRING
)
USING DELTA
COMMENT 'Stato persistente e proposte del retriever BS25 della pagina CODEX';
