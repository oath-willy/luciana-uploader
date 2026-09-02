from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import requests

from services.codex_coherence import decide_bs25ai_route
from services.codex_local_store import CodexSnapshotStore, RuntimeStore


Bs25AiMode = Literal["low", "xhigh"]


class Bs25AiWorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Bs25AiWorkerClient:
    base_url: str
    token: str
    timeout_seconds: int = 900

    @classmethod
    def from_environment(cls) -> "Bs25AiWorkerClient":
        base_url = os.getenv("BS25AI_WORKER_URL", "").strip().rstrip("/")
        token = os.getenv("BS25AI_WORKER_TOKEN", "").strip()
        if not base_url or not token:
            raise Bs25AiWorkerError(
                "Worker BS25AI non configurato: valorizzare BS25AI_WORKER_URL e BS25AI_WORKER_TOKEN"
            )
        timeout = int(os.getenv("BS25AI_WORKER_TIMEOUT_SECONDS", "900"))
        return cls(base_url, token, timeout)

    def review(
        self,
        *,
        request_id: str,
        mode: Bs25AiMode,
        item: dict[str, Any],
        proposals: list[dict[str, Any]],
        taxonomy_coherent: bool,
        routing_flag: str | None,
        thread_id: str | None = None,
        canonical_master_codes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/v1/reviews",
            headers={"Authorization": f"Bearer {self.token}"},
            json={
                "request_id": request_id,
                "mode": mode,
                "thread_id": thread_id,
                "item": {
                    "company": item.get("company"),
                    "item_code": item.get("item_code"),
                    "company_item_code": item.get("company_item_code"),
                    "description": item.get("description"),
                    "details": {
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
                },
                "proposals": proposals,
                "taxonomy_coherent": taxonomy_coherent,
                "routing_flag": routing_flag,
                "canonical_master_codes": canonical_master_codes or [],
            },
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            detail = _response_detail(response)
            raise Bs25AiWorkerError(
                f"Worker BS25AI HTTP {response.status_code}: {detail}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise Bs25AiWorkerError("Il worker BS25AI ha restituito JSON non valido") from exc
        return _validate_worker_response(payload, proposals, mode)

    def complete_goal(self, thread_id: str) -> None:
        response = requests.post(
            f"{self.base_url}/v1/goals/complete",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"thread_id": thread_id},
            timeout=min(self.timeout_seconds, 60),
        )
        if not response.ok:
            raise Bs25AiWorkerError(
                f"Chiusura Goal BS25AI HTTP {response.status_code}: {_response_detail(response)}"
            )


class MockBs25AiWorkerClient:
    """Contract-compatible worker used while lucianavm04 is unavailable."""

    def review(
        self,
        *,
        request_id: str,
        mode: Bs25AiMode,
        item: dict[str, Any],
        proposals: list[dict[str, Any]],
        taxonomy_coherent: bool,
        routing_flag: str | None,
        thread_id: str | None = None,
        canonical_master_codes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del item, routing_flag, canonical_master_codes
        if mode == "low" and not taxonomy_coherent:
            result = {
                "decision": "ambiguous",
                "selected_candidate_rank": None,
                "proposed_master_code": None,
                "confidence": "low",
                "rationale": (
                    "SIMULAZIONE: i candidati tassonomicamente eterogenei "
                    "richiedono la decisione dell'operatore su Sol xhigh."
                ),
                "components": None,
                "evidence": [],
                "simulated": True,
            }
        else:
            first = proposals[0]
            result = {
                "decision": "match",
                "selected_candidate_rank": 1,
                "proposed_master_code": first.get("master_code"),
                "confidence": "medium" if mode == "low" else "high",
                "rationale": (
                    f"SIMULAZIONE {mode}: risposta generata senza contattare lucianavm04."
                ),
                "components": None,
                "evidence": [],
                "simulated": True,
            }
        return {
            "thread_id": thread_id or f"mock-{request_id}",
            "result": result,
        }

    def complete_goal(self, thread_id: str) -> None:
        del thread_id


def worker_from_environment() -> Bs25AiWorkerClient | MockBs25AiWorkerClient:
    if bs25ai_mock_mode():
        return MockBs25AiWorkerClient()
    return Bs25AiWorkerClient.from_environment()


def bs25ai_mock_mode() -> bool:
    configured = os.getenv("BS25AI_MOCK_MODE", "").strip().lower()
    if configured:
        return configured in {"1", "true", "yes", "on"}
    return not (
        os.getenv("BS25AI_WORKER_URL", "").strip()
        and os.getenv("BS25AI_WORKER_TOKEN", "").strip()
    )


def run_bs25ai_job(
    environment: str,
    company: str,
    item_code: str,
    *,
    worker: Bs25AiWorkerClient | None = None,
) -> None:
    snapshot = CodexSnapshotStore(environment)  # type: ignore[arg-type]
    runtime = RuntimeStore()
    job = runtime.get_job(environment, company, item_code)
    if not job:
        return
    try:
        items = snapshot.get_items(company, [item_code])
        if not items:
            raise ValueError("Item non presente nello snapshot locale")
        item = items[0]
        proposals = _proposals(item)
        if len(proposals) != 3:
            raise ValueError("BS25AI richiede esattamente tre proposte BS25")

        decision = decide_bs25ai_route(proposals)
        runtime.update_job(
            environment,
            company,
            item_code,
            status="analyzing",
            stage="bs25_exact" if decision.route == "exact" else "sol_low",
            route=decision.route,
            taxonomy_coherent=int(decision.taxonomy.is_coherent),
            flag=decision.flag,
            error_message=None,
        )
        if decision.route == "exact":
            result = {
                "decision": "match",
                "selected_candidate_rank": 1,
                "proposed_master_code": proposals[0]["master_code"],
                "confidence": "high",
                "rationale": "Corrispondenza descrittiva normalizzata esatta.",
                "components": snapshot.master_code_components(proposals[0]["master_code"]),
                "evidence": [],
            }
            _validate_canonical_result(snapshot, result, proposals, "low")
            _persist_success(runtime, environment, company, item_code, result, None, "complete")
            return

        client = worker or worker_from_environment()
        response = client.review(
            request_id=job["request_id"],
            mode="low",
            item=item,
            proposals=proposals,
            taxonomy_coherent=decision.taxonomy.is_coherent,
            routing_flag=decision.flag,
        )
        _validate_canonical_result(snapshot, response["result"], proposals, "low")
        goal_status = "complete" if response["result"]["decision"] == "match" else "paused"
        _persist_success(
            runtime,
            environment,
            company,
            item_code,
            response["result"],
            response["thread_id"],
            goal_status,
        )
    except Exception as exc:
        runtime.update_job(
            environment,
            company,
            item_code,
            status="failed",
            error_message=str(exc)[:2000],
        )


def run_bs25ai_xhigh(
    environment: str,
    company: str,
    item_code: str,
    *,
    worker: Bs25AiWorkerClient | None = None,
) -> None:
    snapshot = CodexSnapshotStore(environment)  # type: ignore[arg-type]
    runtime = RuntimeStore()
    job = runtime.get_job(environment, company, item_code)
    if not job:
        return
    previous_result = job.get("result")
    try:
        if not job.get("thread_id"):
            raise ValueError("Thread Codex Sol low assente: impossibile continuare in xhigh")
        items = snapshot.get_items(company, [item_code])
        if not items:
            raise ValueError("Item non presente nello snapshot locale")
        item = items[0]
        proposals = _proposals(item)
        runtime.update_job(
            environment,
            company,
            item_code,
            status="analyzing",
            stage="sol_xhigh_web",
            goal_status="active",
            error_message=None,
        )
        client = worker or worker_from_environment()
        response = client.review(
            request_id=job["request_id"],
            mode="xhigh",
            item=item,
            proposals=proposals,
            taxonomy_coherent=bool(job.get("taxonomy_coherent")),
            routing_flag=job.get("flag"),
            thread_id=job["thread_id"],
            canonical_master_codes=snapshot.all_master_codes(),
        )
        _validate_canonical_result(snapshot, response["result"], proposals, "xhigh")
        _persist_success(
            runtime,
            environment,
            company,
            item_code,
            response["result"],
            response["thread_id"],
            "complete",
        )
    except Exception as exc:
        # Keep the last successful low result visible. An xhigh failure never
        # selects or overwrites a code.
        runtime.update_job(
            environment,
            company,
            item_code,
            status="failed",
            result_json=previous_result,
            error_message=str(exc)[:2000],
        )


def complete_human_review_goal(thread_id: str) -> None:
    try:
        worker_from_environment().complete_goal(thread_id)
    except Exception:
        # The local runtime state is authoritative for the webapp. A transient
        # worker failure must not undo the operator's terminal decision.
        return


def _persist_success(
    runtime: RuntimeStore,
    environment: str,
    company: str,
    item_code: str,
    result: dict[str, Any],
    thread_id: str | None,
    goal_status: str,
) -> None:
    runtime.update_job(
        environment,
        company,
        item_code,
        status="completed",
        result_json=result,
        thread_id=thread_id,
        goal_status=goal_status,
        error_message=None,
    )


def _proposals(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item[f"bs25_proposal_{rank}"]
        for rank in (1, 2, 3)
        if isinstance(item.get(f"bs25_proposal_{rank}"), dict)
    ]


def _validate_worker_response(
    payload: Any,
    proposals: list[dict[str, Any]],
    mode: Bs25AiMode,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        raise Bs25AiWorkerError("Risposta worker BS25AI incompleta")
    if not str(payload.get("thread_id") or "").strip():
        raise Bs25AiWorkerError("Il worker BS25AI non ha restituito il thread_id")
    result = payload["result"]
    if result.get("decision") not in {"match", "ambiguous", "unresolved"}:
        raise Bs25AiWorkerError("Decisione BS25AI non valida")
    rank = result.get("selected_candidate_rank")
    if rank is not None and rank not in {1, 2, 3}:
        raise Bs25AiWorkerError("Rank candidato BS25AI non valido")
    if result.get("decision") == "match" and not str(
        result.get("proposed_master_code") or ""
    ).strip():
        raise Bs25AiWorkerError("Match BS25AI privo di Master Code")
    if mode == "low" and rank is None and result.get("decision") == "match":
        raise Bs25AiWorkerError("Sol low puo scegliere soltanto uno dei tre candidati")
    if mode == "low" and rank is not None:
        expected = str(proposals[rank - 1].get("master_code") or "").strip().upper()
        actual = str(result.get("proposed_master_code") or "").strip().upper()
        if expected != actual:
            raise Bs25AiWorkerError("Sol low ha restituito un codice diverso dal candidato scelto")
    result.setdefault("confidence", None)
    result.setdefault("rationale", "")
    result.setdefault("components", None)
    result.setdefault("evidence", [])
    return {"thread_id": str(payload["thread_id"]), "result": result}


def _validate_canonical_result(
    snapshot: CodexSnapshotStore,
    result: dict[str, Any],
    proposals: list[dict[str, Any]],
    mode: Bs25AiMode,
) -> None:
    if result.get("decision") != "match":
        return
    code = str(result.get("proposed_master_code") or "").strip().upper()
    if not snapshot.has_master_code(code):
        raise Bs25AiWorkerError(f"Master Code BS25AI non presente nello snapshot canonico: {code}")
    if mode == "low" and code not in {
        str(item.get("master_code") or "").strip().upper() for item in proposals
    }:
        raise Bs25AiWorkerError("Sol low non puo proporre codici fuori dalla Top-3")


def _response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("detail") or payload)[:500]
    except ValueError:
        return response.text[:500]
