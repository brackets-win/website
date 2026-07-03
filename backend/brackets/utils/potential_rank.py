"""
Best achievable leaderboard rank across all master knockout completions.

Potential rank enumerates every completion of undecided matchups (not just the
highest-scoring branch) and tracks the best achievable rank per entry.

Potential points live in potential_score.py — this module never writes them.
"""

from __future__ import annotations

import numpy as np

from brackets.models import Bracket, BracketStage, UserBracket
from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
from brackets.utils.potential_knockout import (
    KnockoutScoringParams,
    TreeState,
    enumerate_completions,
    master_stage_mask,
    prepare_knockout_potential,
    winner_bonus,
)

MAX_UNDECIDED_MATCHUPS = 16
MAX_BATCH_SIZE = 4096
MIN_BATCH_SIZE = 32
MAX_BATCH_MEMORY_BYTES = 64 * 1024 * 1024


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
    if ctx.master is None or not ubs:
        return {}

    has_knockout = any(
        s.stage_type == BracketStage.StageType.KNOCKOUT for s in ctx.stages
    )
    if not has_knockout:
        return {ub.id: 1 for ub in ubs}

    prepared = prepare_knockout_potential(ctx, ubs)
    if prepared is None:
        return None

    if prepared.branchable > cap:
        return {ub.id: None for ub in ubs}

    n_players = len(ubs)
    ranks_by_idx = _best_ranks_via_batch_enum(
        prepared.tree,
        prepared.scoring,
        n_players=n_players,
        champ_pts=prepared.champ_pts,
        third_pts=prepared.third_pts,
    )
    if ranks_by_idx is None:
        return {ub.id: None for ub in ubs}

    return {
        ub.id: ranks_by_idx[i] if ranks_by_idx[i] <= n_players else None
        for i, ub in enumerate(ubs)
    }


def persist_potential_ranks_for_bracket(bracket: Bracket) -> None:
    """Compute and store potential rank on all submitted entries."""
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket

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

    for ub in qs:
        rank = ranks.get(ub.id)
        if ub.leaderboard_potential_rank != rank:
            ub.leaderboard_potential_rank = rank
            ub.save(update_fields=["leaderboard_potential_rank"])


def _best_ranks_via_batch_enum(
    tree: TreeState,
    scoring: KnockoutScoringParams,
    *,
    n_players: int,
    champ_pts: float,
    third_pts: float,
) -> dict[int, int] | None:
    n_stages = len(scoring.main_ko_stages)
    n_teams = len(scoring.team_to_idx)
    batch_size = _completion_batch_size(n_players, n_stages, n_teams)

    best_ranks = np.full(n_players, n_players + 1, dtype=np.int32)
    batch_masks: list[np.ndarray] = []
    batch_champ_bonus: list[np.ndarray] = []
    batch_third_bonus: list[np.ndarray] = []

    def flush_batch() -> None:
        nonlocal best_ranks
        if not batch_masks:
            return
        master_mask = np.stack(batch_masks, axis=0)
        weighted_user = scoring.user_mask * scoring.stage_pts[np.newaxis, :, np.newaxis]
        completion_ko = np.einsum("pst,bst->bp", weighted_user, master_mask)
        completion_marginal = completion_ko
        if champ_pts > 0 and batch_champ_bonus:
            completion_marginal = completion_marginal + np.stack(batch_champ_bonus, axis=0)
        if third_pts > 0 and batch_third_bonus:
            completion_marginal = completion_marginal + np.stack(batch_third_bonus, axis=0)
        totals = (
            scoring.current_totals[np.newaxis, :]
            + completion_marginal
            - scoring.current_ko_bonus
        )
        ranks = competition_ranks_batch(totals)
        best_ranks = np.minimum(best_ranks, np.min(ranks, axis=0))
        batch_masks.clear()
        batch_champ_bonus.clear()
        batch_third_bonus.clear()

    def record_completion(state: TreeState) -> None:
        batch_masks.append(
            master_stage_mask(
                state,
                scoring.main_ko_stages,
                scoring.ko_stages,
                scoring.team_to_idx,
            )
        )
        batch_champ_bonus.append(
            winner_bonus(
                state,
                scoring.final_m_idx,
                scoring.user_champ,
                scoring.team_to_idx,
            )
        )
        batch_third_bonus.append(
            winner_bonus(
                state,
                scoring.third_m_idx,
                scoring.user_third,
                scoring.team_to_idx,
            )
        )
        if len(batch_masks) >= batch_size:
            flush_batch()

    enumerate_completions(tree, record_completion)
    flush_batch()

    if np.all(best_ranks > n_players):
        return None

    return {i: int(best_ranks[i]) for i in range(n_players)}


def _completion_batch_size(n_players: int, n_stages: int, n_teams: int) -> int:
    per_completion = n_stages * n_teams * 8 + 40 * n_players
    per_completion = max(per_completion, 1)
    batch = MAX_BATCH_MEMORY_BYTES // per_completion
    return int(max(MIN_BATCH_SIZE, min(MAX_BATCH_SIZE, batch)))


def competition_ranks_batch(totals: np.ndarray) -> np.ndarray:
    """Competition ranks for each completion row in ``totals`` (B, N)."""
    if totals.ndim != 2:
        raise ValueError("totals must be a 2-D array")
    batch_size, n_players = totals.shape
    if n_players == 0:
        return np.empty((batch_size, 0), dtype=np.int32)

    order = np.argsort(-totals, axis=1, kind="mergesort")
    sorted_scores = np.take_along_axis(totals, order, axis=1)
    ranks_sorted = np.ones((batch_size, n_players), dtype=np.int32)
    if n_players > 1:
        tie = sorted_scores[:, 1:] == sorted_scores[:, :-1]
        for i in range(1, n_players):
            ranks_sorted[:, i] = np.where(
                tie[:, i - 1],
                ranks_sorted[:, i - 1],
                i + 1,
            )
    ranks = np.empty((batch_size, n_players), dtype=np.int32)
    np.put_along_axis(ranks, order, ranks_sorted, axis=1)
    return ranks
