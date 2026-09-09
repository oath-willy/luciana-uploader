from dataclasses import dataclass
from typing import Any, Literal, Sequence


EXPECTED_BS25_CANDIDATES = 3

Bs25TaxonomyReason = Literal[
    "coherent_taxonomy",
    "heterogeneous_taxonomy",
    "insufficient_candidates",
    "missing_taxonomy",
]
Bs25AiRoute = Literal["exact", "sol_low"]


@dataclass(frozen=True)
class Bs25TaxonomyAssessment:
    is_coherent: bool
    reason: Bs25TaxonomyReason


@dataclass(frozen=True)
class Bs25AiRoutingDecision:
    route: Bs25AiRoute
    taxonomy: Bs25TaxonomyAssessment
    flag: str | None


def assess_candidate_taxonomy(
    proposals: Sequence[dict[str, Any]],
) -> Bs25TaxonomyAssessment:
    """Describe top-3 taxonomic agreement without using it as a router.

    The stable taxonomy key is the first two Master Code levels. This signal is
    diagnostic only: results from a fuzzy search always go through Sol low.
    """
    if len(proposals) != EXPECTED_BS25_CANDIDATES:
        return Bs25TaxonomyAssessment(False, "insufficient_candidates")

    keys = [_taxonomy_key(item.get("master_code")) for item in proposals]
    if any(key is None for key in keys):
        return Bs25TaxonomyAssessment(False, "missing_taxonomy")
    if len(set(keys)) != 1:
        return Bs25TaxonomyAssessment(False, "heterogeneous_taxonomy")
    return Bs25TaxonomyAssessment(True, "coherent_taxonomy")


def decide_bs25ai_route(
    proposals: Sequence[dict[str, Any]],
) -> Bs25AiRoutingDecision:
    taxonomy = assess_candidate_taxonomy(proposals)
    first = proposals[0] if proposals else {}
    if (
        len(proposals) == EXPECTED_BS25_CANDIDATES
        and bool(first.get("exact_match"))
        and bool(str(first.get("master_code") or "").strip())
    ):
        return Bs25AiRoutingDecision("exact", taxonomy, None)

    suffix = (
        "Candidati BS25 tassonomicamente coerenti."
        if taxonomy.is_coherent
        else "Candidati BS25 tassonomicamente eterogenei o incompleti."
    )
    return Bs25AiRoutingDecision(
        "sol_low",
        taxonomy,
        f"Ricerca fuzzy non conclusiva: analisi LLM avviata automaticamente. {suffix}",
    )


def _taxonomy_key(value: Any) -> tuple[str, str] | None:
    parts = str(value or "").strip().upper().split("_")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]
