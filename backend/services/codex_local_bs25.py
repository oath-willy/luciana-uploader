from __future__ import annotations

from typing import Any

from services.codex_local_retrieval import (
    LOCAL_RETRIEVER_VERSION,
    LocalPdbBm25Retriever,
)
from services.codex_local_store import CodexSnapshotStore, RuntimeStore


def run_local_bs25_batch(
    environment: str,
    company: str,
    item_codes: list[str],
    *,
    retriever: LocalPdbBm25Retriever | None = None,
) -> None:
    snapshot = CodexSnapshotStore(environment)  # type: ignore[arg-type]
    runtime = RuntimeStore()
    items = snapshot.get_items(company, item_codes)
    items_by_code = {str(item["item_code"]): item for item in items}
    active: list[dict[str, Any]] = []
    for item_code in item_codes:
        if item_code not in items_by_code:
            runtime.update_bs25_job(
                environment,
                company,
                item_code,
                status="failed",
                error_message="Item non presente nello snapshot CODEX locale",
            )
            continue
        runtime.update_bs25_job(
            environment,
            company,
            item_code,
            status="analyzing",
            error_message=None,
        )
        active.append(items_by_code[item_code])

    if not active:
        return
    try:
        proposals_by_code = (retriever or LocalPdbBm25Retriever(environment)).retrieve(active)
        for item in active:
            item_code = str(item["item_code"])
            proposals = proposals_by_code[item_code]
            runtime.update_bs25_job(
                environment,
                company,
                item_code,
                status="completed",
                proposal_1_json=proposals[0],
                proposal_2_json=proposals[1],
                proposal_3_json=proposals[2],
                retriever_version=LOCAL_RETRIEVER_VERSION,
                error_message=None,
            )
    except Exception as exc:
        for item in active:
            runtime.update_bs25_job(
                environment,
                company,
                str(item["item_code"]),
                status="failed",
                error_message=str(exc)[:2000],
            )
