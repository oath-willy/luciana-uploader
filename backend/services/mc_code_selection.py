from dataclasses import dataclass
from typing import Literal


SelectionKind = Literal["proposal", "clear"]


@dataclass(frozen=True)
class McCodeSelection:
    kind: SelectionKind
    proposal_rank: int | None = None
    master_code: str | None = None


def resolve_mc_code_selection(
    proposal_rank: int | None,
    clear: bool,
) -> McCodeSelection:
    requested_actions = sum((proposal_rank is not None, bool(clear)))
    if requested_actions != 1:
        raise ValueError("Indica una sola scelta: proposta BS25 o cancellazione")

    if proposal_rank is not None:
        if proposal_rank not in {1, 2, 3}:
            raise ValueError("La proposta BS25 deve essere compresa tra 1 e 3")
        return McCodeSelection("proposal", proposal_rank=proposal_rank)

    return McCodeSelection("clear")
