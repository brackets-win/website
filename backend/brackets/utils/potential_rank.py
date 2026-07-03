"""
Best achievable leaderboard rank across all master knockout completions.

Potential rank enumerates every completion of undecided matchups (not just the
highest-scoring branch) and tracks the best achievable rank per entry.

Potential points live in potential_score.py — this module never writes them.
"""

from __future__ import annotations

from brackets.models import Bracket, UserBracket
from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
from brackets.utils.potential_knockout import competition_ranks_batch

MAX_UNDECIDED_MATCHUPS = 16

# Re-export for tests and callers that imported from here.
__all__ = [
    "MAX_UNDECIDED_MATCHUPS",
    "competition_ranks_batch",
    "compute_potential_ranks_for_bracket",
    "persist_potential_ranks_for_bracket",
]


def compute_potential_ranks_for_bracket(
    bracket: Bracket,
    *,
    cap: int = MAX_UNDECIDED_MATCHUPS,
) -> dict[int, int | None] | None:
    """
    Return best achievable rank per submitted user bracket id.

    Returns ``None`` when rank cannot be enumerated (too many branchable games
    or first knockout round not fully seeded).
    """
    ctx = load_leaderboard_scoring_context(bracket)
    ubs = list(
        UserBracket.objects.filter(
            bracket=bracket,
            is_master=False,
            submitted_at__isnull=False,
        ).prefetch_related("matchup_set")
    )
    return compute_potential_ranks_for_users(ctx, ubs, cap=cap)


def compute_potential_ranks_for_users(
    ctx,
    ubs: list[UserBracket],
    *,
    cap: int = MAX_UNDECIDED_MATCHUPS,
) -> dict[int, int | None] | None:
    from brackets.utils.potential_score import _compute_potential_outcomes

    outcomes = _compute_potential_outcomes(ctx, ubs, rank_cap=cap)
    if outcomes is None:
        return None
    _scores, ranks = outcomes
    return ranks


def persist_potential_ranks_for_bracket(bracket: Bracket) -> None:
    """Compute and store potential rank on all submitted entries."""
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket
    from brackets.utils.potential_score import _write_potential_ranks

    qs = UserBracket.objects.filter(
        bracket=bracket,
        is_master=False,
        submitted_at__isnull=False,
    )
    if omit_leaderboard_potential_for_bracket(bracket):
        return

    ranks = compute_potential_ranks_for_bracket(bracket)
    if ranks is None:
        qs.update(leaderboard_potential_rank=None)
        return

    _write_potential_ranks(list(qs), ranks)
