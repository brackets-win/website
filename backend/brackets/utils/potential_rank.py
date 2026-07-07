"""
Best achievable leaderboard rank across all master knockout completions.

Potential rank enumerates every completion of undecided matchups (not just the
highest-scoring branch) and tracks the best achievable rank per entry.

Potential points live in potential_score.py — this module never writes them.
"""

from __future__ import annotations

from brackets.models import Bracket, BracketStage, UserBracket
from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
from brackets.utils.potential_knockout import (
    competition_ranks_batch,
    first_knockout_fully_seeded,
)

# Potential Rank appears only once the earliest incomplete main knockout stage
# is quarter-finals or later (≤ 4 matchups in that stage on the master bracket).
MAX_EARLIEST_INCOMPLETE_STAGE_MATCHUPS_FOR_RANK = 4

# Legacy name kept for tests that force rank enumeration off via cap=0.
MAX_UNDECIDED_MATCHUPS = MAX_EARLIEST_INCOMPLETE_STAGE_MATCHUPS_FOR_RANK

__all__ = [
    "MAX_EARLIEST_INCOMPLETE_STAGE_MATCHUPS_FOR_RANK",
    "MAX_UNDECIDED_MATCHUPS",
    "competition_ranks_batch",
    "compute_potential_ranks_for_bracket",
    "compute_potential_ranks_for_challenge",
    "persist_potential_ranks_for_bracket",
    "potential_rank_allowed_for_bracket",
    "potential_rank_allowed_for_context",
]


def potential_rank_allowed_for_context(ctx) -> bool:
    """
    True when the master bracket's earliest incomplete main knockout stage has
    at most four matchups (quarter-finals or later).
    """
    master = ctx.master
    if master is None:
        return False

    ko_stages = [
        s for s in ctx.stages if s.stage_type == BracketStage.StageType.KNOCKOUT
    ]
    main_ko_stages = [
        s for s in ko_stages if not ctx.knockout_by_id[s.pk].is_third_place
    ]
    if main_ko_stages and not first_knockout_fully_seeded(master, main_ko_stages[0]):
        return False

    for stage in main_ko_stages:
        matchups = list(master.matchup_set.filter(stage=stage))
        if not matchups:
            continue
        if all(m.winner_id is not None for m in matchups):
            continue
        return (
            len(matchups) <= MAX_EARLIEST_INCOMPLETE_STAGE_MATCHUPS_FOR_RANK
        )

    return True


def potential_rank_allowed_for_bracket(bracket: Bracket) -> bool:
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket

    if omit_leaderboard_potential_for_bracket(bracket):
        return False
    ctx = load_leaderboard_scoring_context(bracket)
    return potential_rank_allowed_for_context(ctx)


def _submitted_pools_for_bracket(bracket: Bracket) -> list[list[UserBracket]]:
    """
    Submitted entry pools for rank — one pool per challenge (or one pool for
    entries with no challenge). Rank is always relative within a pool only.
    """
    ubs = list(
        UserBracket.objects.filter(
            bracket=bracket,
            is_master=False,
            submitted_at__isnull=False,
        )
        .prefetch_related("matchup_set")
        .order_by("challenge_id", "id")
    )
    if not ubs:
        return []

    pools: list[list[UserBracket]] = []
    current_key = ubs[0].challenge_id
    current: list[UserBracket] = []
    for ub in ubs:
        if ub.challenge_id != current_key:
            pools.append(current)
            current_key = ub.challenge_id
            current = []
        current.append(ub)
    if current:
        pools.append(current)
    return pools


def compute_potential_ranks_for_challenge(
    challenge,
) -> dict[int, int | None] | None:
    """Best achievable rank per submitted entry in one challenge pool."""
    from brackets.models import BracketChallenge

    if not isinstance(challenge, BracketChallenge):
        raise TypeError("challenge must be a BracketChallenge")

    bracket = challenge.bracket
    if not potential_rank_allowed_for_bracket(bracket):
        return {
            ub.id: None
            for ub in UserBracket.objects.filter(
                challenge=challenge,
                is_master=False,
                submitted_at__isnull=False,
            )
        }

    ctx = load_leaderboard_scoring_context(bracket)
    ubs = list(
        UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            submitted_at__isnull=False,
        ).prefetch_related("matchup_set")
    )
    return compute_potential_ranks_for_users(ctx, ubs)


def compute_potential_ranks_for_bracket(
    bracket: Bracket,
    *,
    cap: int = MAX_EARLIEST_INCOMPLETE_STAGE_MATCHUPS_FOR_RANK,
) -> dict[int, int | None] | None:
    """
    Return best achievable rank per submitted user bracket id.

    Ranks are computed separately within each challenge pool on a reusable
    bracket — never across challenges.

    Returns ``None`` when rank cannot be enumerated (gate closed or tree not ready).
    """
    del cap
    submitted = UserBracket.objects.filter(
        bracket=bracket,
        is_master=False,
        submitted_at__isnull=False,
    )
    if not potential_rank_allowed_for_bracket(bracket):
        return {ub.id: None for ub in submitted}

    ctx = load_leaderboard_scoring_context(bracket)
    merged: dict[int, int | None] = {}
    for pool in _submitted_pools_for_bracket(bracket):
        pool_ranks = compute_potential_ranks_for_users(ctx, pool)
        if pool_ranks is None:
            return None
        merged.update(pool_ranks)
    return merged


def compute_potential_ranks_for_users(
    ctx,
    ubs: list[UserBracket],
) -> dict[int, int | None] | None:
    from brackets.utils.potential_score import _compute_potential_outcomes

    if not potential_rank_allowed_for_context(ctx):
        return {ub.id: None for ub in ubs}

    outcomes = _compute_potential_outcomes(ctx, ubs, compute_ranks=True)
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

    if not potential_rank_allowed_for_bracket(bracket):
        qs.update(leaderboard_potential_rank=None)
        return

    ranks = compute_potential_ranks_for_bracket(bracket)
    if ranks is None:
        qs.update(leaderboard_potential_rank=None)
        return

    _write_potential_ranks(list(qs), ranks)
