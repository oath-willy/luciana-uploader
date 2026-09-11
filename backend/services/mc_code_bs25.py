from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

import requests

from services.mc_code_local_store import McCodeSnapshotStore, RuntimeStore


MAX_BS25_BATCH_SIZE = 20


class Bs25WorkerError(RuntimeError):
    pass


class Bs25Retriever(Protocol):
    retriever_version: str

    def retrieve(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]: ...


@dataclass(frozen=True)
class Bs25WorkerClient:
    endpoint: ClassVar[str] = "/v1/bs25"
    retriever_version: ClassVar[str] = "pdb-bm25-vm04-v1"
    base_url: str
    token: str
    timeout_seconds: int = 180

    @classmethod
    def from_environment(cls) -> "Bs25WorkerClient":
        base_url = os.getenv("BS25_WORKER_URL", "").strip().rstrip("/")
        token = os.getenv("BS25_WORKER_TOKEN", "").strip()
        if not base_url or not token:
            raise Bs25WorkerError(
                "Worker BS25 su lucianavm04 non configurato: valorizzare "
                "BS25_WORKER_URL e BS25_WORKER_TOKEN"
            )
        timeout = int(os.getenv("BS25_WORKER_TIMEOUT_SECONDS", "180"))
        return cls(base_url, token, timeout)

    def retrieve(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        if not items:
            return {}
        if len(items) > MAX_BS25_BATCH_SIZE:
            raise ValueError(
                f"Seleziona al massimo {MAX_BS25_BATCH_SIZE} record per analisi BS25"
            )
        outgoing = [_worker_item(item) for item in items]
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"items": outgoing},
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise Bs25WorkerError(
                f"Worker BS25 HTTP {response.status_code}: {_response_detail(response)}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise Bs25WorkerError("Il worker BS25 ha restituito JSON non valido") from exc
        return _validate_response(payload, outgoing)


class Bs23V2WorkerClient(Bs25WorkerClient):
    endpoint = "/v1/bs23-v2"
    retriever_version = "pdb-coding-proposals-v2"


def bs25_worker_configured() -> bool:
    return bool(
        os.getenv("BS25_WORKER_URL", "").strip()
        and os.getenv("BS25_WORKER_TOKEN", "").strip()
    )


def run_bs25_batch(
    environment: str,
    company: str,
    item_codes: list[str],
    *,
    retriever: Bs25Retriever | None = None,
) -> None:
    _run_bs25_batch(
        environment,
        company,
        item_codes,
        retriever=retriever or Bs25WorkerClient.from_environment(),
    )


def run_bs23_v2_batch(
    environment: str,
    company: str,
    item_codes: list[str],
    *,
    retriever: Bs25Retriever | None = None,
) -> None:
    _run_bs25_batch(
        environment,
        company,
        item_codes,
        retriever=retriever or Bs23V2WorkerClient.from_environment(),
    )


def _run_bs25_batch(
    environment: str,
    company: str,
    item_codes: list[str],
    *,
    retriever: Bs25Retriever,
) -> None:
    snapshot = McCodeSnapshotStore(environment)  # type: ignore[arg-type]
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
                error_message="Item non presente nello snapshot MC CODE locale",
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
        proposals_by_code = retriever.retrieve(active)
        version = getattr(retriever, "retriever_version", "pdb-bm25-vm04-v1")
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
                retriever_version=version,
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


def _worker_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": str(item.get("company") or "").strip(),
        "item_code": str(item.get("item_code") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "extra": {
            key: value
            for key, value in item.items()
            if key
            not in {
                "id",
                "company",
                "item_code",
                "company_item_code",
                "description",
            }
            and not key.startswith("bs25_")
            and not key.startswith("aibs25_")
        },
    }


def _validate_response(
    payload: Any, requested: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise Bs25WorkerError("Risposta worker BS25 incompleta")
    version = str(payload.get("retriever_version") or "").strip()
    if not version:
        raise Bs25WorkerError("Versione retriever BS25 assente")

    expected = {
        (item["company"].casefold(), item["item_code"]): item for item in requested
    }
    results: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for result in payload["results"]:
        if not isinstance(result, dict):
            raise Bs25WorkerError("Risultato worker BS25 non valido")
        key = (
            str(result.get("company") or "").strip().casefold(),
            str(result.get("item_code") or "").strip(),
        )
        if key not in expected or key in seen:
            raise Bs25WorkerError("Item inatteso o duplicato nella risposta BS25")
        proposals = result.get("proposals")
        if not isinstance(proposals, list) or len(proposals) != 3:
            raise Bs25WorkerError("Il worker BS25 deve restituire tre proposte per item")
        validated = [
            _validate_proposal(proposal, rank, version)
            for rank, proposal in enumerate(proposals, start=1)
        ]
        seen.add(key)
        results[key[1]] = validated
    if seen != set(expected):
        raise Bs25WorkerError("La risposta BS25 non contiene tutti gli item richiesti")
    return results


def _validate_proposal(
    proposal: Any, expected_rank: int, version: str
) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        raise Bs25WorkerError("Proposta BS25 non valida")
    try:
        rank = int(proposal.get("identity_rank"))
        score = float(proposal.get("identity_score"))
    except (TypeError, ValueError) as exc:
        raise Bs25WorkerError("Rank o score BS25 non valido") from exc
    if rank != expected_rank or not math.isfinite(score) or score < 0:
        raise Bs25WorkerError("Ordine o score delle proposte BS25 non valido")
    if not str(proposal.get("pdb_ref") or "").strip():
        raise Bs25WorkerError("Proposta BS25 priva di riferimento PDB")
    if not str(proposal.get("master_code") or "").strip():
        raise Bs25WorkerError("Proposta BS25 priva di Master Code")
    return {
        **proposal,
        "identity_rank": rank,
        "identity_score": score,
        "exact_match": bool(proposal.get("exact_match")),
        "retriever_version": str(proposal.get("retriever_version") or version),
    }


def _response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("detail") or payload)[:500]
    except ValueError:
        return response.text[:500]
