from dataclasses import dataclass
from typing import Literal


SelectionKind = Literal["proposal", "clear"]


@dataclass(frozen=True)
class CodexSelection:
    kind: SelectionKind
    proposal_rank: int | None = None
    master_code: str | None = None


def resolve_codex_selection(
    proposal_rank: int | None,
    clear: bool,
) -> CodexSelection:
    requested_actions = sum((proposal_rank is not None, bool(clear)))
    if requested_actions != 1:
        raise ValueError("Indica una sola scelta: proposta BS25 o cancellazione")

    if proposal_rank is not None:
        if proposal_rank not in {1, 2, 3}:
            raise ValueError("La proposta BS25 deve essere compresa tra 1 e 3")
        return CodexSelection("proposal", proposal_rank=proposal_rank)

    return CodexSelection("clear")
