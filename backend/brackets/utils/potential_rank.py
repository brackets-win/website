"""
Best achievable leaderboard rank across all completions of the master knockout tree.

Group points are fixed (Confirmed mode). Remaining master knockout winners are
enumerated exactly; for each completion every submitted bracket is scored vs
that master state and competition ranks are tracked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from brackets.models import Bracket, BracketStage, KnockoutStage, UserBracket
from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
from brackets.utils.sync_group_knockout import (
    contestants_credited_for_knockout_score,
    projected_first_knockout_contestant_ids,
)

MAX_UNDECIDED_MATCHUPS = 16
MAX_BATCH_SIZE = 4096
MIN_BATCH_SIZE = 32
# Soft cap on transient batch arrays (master masks + totals + rank workspace).
MAX_BATCH_MEMORY_BYTES = 64 * 1024 * 1024


@dataclass
class _MemMatchup:
    stage_idx: int
    position: int
    c1: int | None = None
    c2: int | None = None
    winner: int | None = None
    next_idx: int | None = None
    is_team_a: bool = False
    feeds: list[tuple[int, str, bool]] = field(default_factory=list)


@dataclass
class _TreeState:
    matchups: list[_MemMatchup]
    stage_matchup_indices: list[list[int]]


def compute_potential_ranks_for_bracket(
    bracket: Bracket,
    *,
    cap: int = MAX_UNDECIDED_MATCHUPS,
) -> dict[int, int | None] | None:
    """
    Return best achievable rank per submitted user bracket id.

    Returns ``None`` when the bracket cannot be enumerated (e.g. too many
    undecided matchups or first knockout round not fully seeded).
    """
    ctx = load_leaderboard_scoring_context(bracket)
    master = ctx.master
    if master is None:
        return {}

    ubs = list(
        UserBracket.objects.filter(
            bracket=bracket,
            is_master=False,
            submitted_at__isnull=False,
        ).prefetch_related("matchup_set")
    )
    if not ubs:
        return {}

    ko_stages = [
        s
        for s in ctx.stages
        if s.stage_type == BracketStage.StageType.KNOCKOUT
    ]
    if not ko_stages:
        return {ub.id: 1 for ub in ubs}

    main_ko_stages = [
        s
        for s in ko_stages
        if not ctx.knockout_by_id[s.pk].is_third_place
    ]
    third_stage = next(
        (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_third_place),
        None,
    )
    final_stage = next(
        (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_final),
        None,
    )

    if main_ko_stages and not _first_knockout_fully_seeded(master, main_ko_stages[0]):
        return None

    tree = _build_master_tree(master, ko_stages)
    undecided = _count_undecided_matchups(tree)
    if undecided > cap:
        return None

    team_ids = _collect_team_ids(ubs, master, ko_stages, ctx)
    team_to_idx = {tid: i for i, tid in enumerate(sorted(team_ids))}
    if not team_to_idx:
        return {ub.id: 1 for ub in ubs}

    n_players = len(ubs)
    base = _base_group_scores(ubs, ctx)
    stage_pts = np.array(
        [
            float(ctx.knockout_by_id[s.pk].points_per_correct_pick)
            for s in main_ko_stages
        ],
        dtype=np.float64,
    )
    user_mask = _user_knockout_mask(ubs, main_ko_stages, team_to_idx)
    champ_pts = float(bracket.points_champion or 0)
    third_pts = float(bracket.points_third_place_winner or 0)
    user_champ = _user_winner_matrix(ubs, final_stage, team_to_idx, champ_pts)
    user_third = _user_winner_matrix(ubs, third_stage, team_to_idx, third_pts)

    final_m_idx = _final_matchup_index(tree, ko_stages, final_stage)
    third_m_idx = _final_matchup_index(tree, ko_stages, third_stage)

    n_stages = len(main_ko_stages)
    n_teams = len(team_to_idx)
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
        weighted_user = user_mask * stage_pts[np.newaxis, :, np.newaxis]
        ko = np.einsum("pst,bst->bp", weighted_user, master_mask)
        totals = base[np.newaxis, :] + ko
        if champ_pts > 0 and batch_champ_bonus:
            totals += np.stack(batch_champ_bonus, axis=0)
        if third_pts > 0 and batch_third_bonus:
            totals += np.stack(batch_third_bonus, axis=0)
        ranks = _competition_ranks_batch(totals)
        best_ranks = np.minimum(best_ranks, np.min(ranks, axis=0))
        batch_masks.clear()
        batch_champ_bonus.clear()
        batch_third_bonus.clear()

    def record_completion(state: _TreeState) -> None:
        batch_masks.append(
            _master_stage_mask(state, main_ko_stages, ko_stages, team_to_idx)
        )
        batch_champ_bonus.append(
            _winner_bonus(state, final_m_idx, user_champ, team_to_idx)
        )
        batch_third_bonus.append(
            _winner_bonus(state, third_m_idx, user_third, team_to_idx)
        )
        if len(batch_masks) >= batch_size:
            flush_batch()

    _enumerate_completions(tree, record_completion)
    flush_batch()

    if np.all(best_ranks > n_players):
        return None

    out: dict[int, int | None] = {}
    for i, ub in enumerate(ubs):
        rank = int(best_ranks[i])
        out[ub.id] = rank if rank <= n_players else None
    return out


def compute_next_match_side_ranks_for_bracket(
    bracket: Bracket,
    next_stage_id: int,
    next_position: int,
    side1_contestant_id: int,
    *,
    cap: int = MAX_UNDECIDED_MATCHUPS,
) -> dict[int, tuple[int | None, int | None]] | None:
    """Best achievable rank per submitted entry split by the next match outcome.

    Returns ``{ub_id: (best_rank_if_side1_wins, best_rank_if_side2_wins)}`` where
    each rank may be ``None`` when that side never occurs. Returns ``None`` when
    the master knockout tree cannot be enumerated (same gate as
    :func:`compute_potential_ranks_for_bracket`).
    """
    ctx = load_leaderboard_scoring_context(bracket)
    master = ctx.master
    if master is None:
        return None

    ubs = list(
        UserBracket.objects.filter(
            bracket=bracket,
            is_master=False,
            submitted_at__isnull=False,
        ).prefetch_related("matchup_set")
    )
    if not ubs:
        return {}

    ko_stages = [
        s
        for s in ctx.stages
        if s.stage_type == BracketStage.StageType.KNOCKOUT
    ]
    if not ko_stages:
        return None

    main_ko_stages = [
        s
        for s in ko_stages
        if not ctx.knockout_by_id[s.pk].is_third_place
    ]
    third_stage = next(
        (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_third_place),
        None,
    )
    final_stage = next(
        (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_final),
        None,
    )

    if main_ko_stages and not _first_knockout_fully_seeded(master, main_ko_stages[0]):
        return None

    tree = _build_master_tree(master, ko_stages)
    next_m_idx = _tree_matchup_index(tree, ko_stages, next_stage_id, next_position)
    if next_m_idx is None:
        return None

    next_m = tree.matchups[next_m_idx]
    if next_m.winner is not None:
        return None

    side2_contestant_id = (
        next_m.c2 if side1_contestant_id == next_m.c1 else next_m.c1
    )
    if side2_contestant_id is None:
        return None

    pinned_probe = _copy_state(tree)
    _apply_winner(pinned_probe, next_m_idx, side1_contestant_id)
    if _count_undecided_matchups(pinned_probe) > cap:
        return None

    team_ids = _collect_team_ids(ubs, master, ko_stages, ctx)
    team_to_idx = {tid: i for i, tid in enumerate(sorted(team_ids))}
    if not team_to_idx:
        return None

    n_players = len(ubs)
    base = _base_group_scores(ubs, ctx)
    stage_pts = np.array(
        [
            float(ctx.knockout_by_id[s.pk].points_per_correct_pick)
            for s in main_ko_stages
        ],
        dtype=np.float64,
    )
    user_mask = _user_knockout_mask(ubs, main_ko_stages, team_to_idx)
    champ_pts = float(bracket.points_champion or 0)
    third_pts = float(bracket.points_third_place_winner or 0)
    user_champ = _user_winner_matrix(ubs, final_stage, team_to_idx, champ_pts)
    user_third = _user_winner_matrix(ubs, third_stage, team_to_idx, third_pts)

    final_m_idx = _final_matchup_index(tree, ko_stages, final_stage)
    third_m_idx = _final_matchup_index(tree, ko_stages, third_stage)

    n_stages = len(main_ko_stages)
    n_teams = len(team_to_idx)
    batch_size = _completion_batch_size(n_players, n_stages, n_teams)

    best_side1 = np.full(n_players, n_players + 1, dtype=np.int32)
    best_side2 = np.full(n_players, n_players + 1, dtype=np.int32)

    def enumerate_pinned_side(
        winner_id: int, best: np.ndarray
    ) -> bool:
        pinned = _copy_state(tree)
        _apply_winner(pinned, next_m_idx, winner_id)
        if _count_undecided_matchups(pinned) > cap:
            return False

        batch_masks: list[np.ndarray] = []
        batch_champ_bonus: list[np.ndarray] = []
        batch_third_bonus: list[np.ndarray] = []

        def flush_batch() -> None:
            nonlocal best
            if not batch_masks:
                return
            master_mask = np.stack(batch_masks, axis=0)
            weighted_user = user_mask * stage_pts[np.newaxis, :, np.newaxis]
            ko = np.einsum("pst,bst->bp", weighted_user, master_mask)
            totals = base[np.newaxis, :] + ko
            if champ_pts > 0 and batch_champ_bonus:
                totals += np.stack(batch_champ_bonus, axis=0)
            if third_pts > 0 and batch_third_bonus:
                totals += np.stack(batch_third_bonus, axis=0)
            ranks = _competition_ranks_batch(totals)
            best = np.minimum(best, np.min(ranks, axis=0))
            batch_masks.clear()
            batch_champ_bonus.clear()
            batch_third_bonus.clear()

        def record_completion(state: _TreeState) -> None:
            batch_masks.append(
                _master_stage_mask(state, main_ko_stages, ko_stages, team_to_idx)
            )
            batch_champ_bonus.append(
                _winner_bonus(state, final_m_idx, user_champ, team_to_idx)
            )
            batch_third_bonus.append(
                _winner_bonus(state, third_m_idx, user_third, team_to_idx)
            )
            if len(batch_masks) >= batch_size:
                flush_batch()

        _enumerate_completions(tree, record_completion, state=pinned)
        flush_batch()
        return True

    if not enumerate_pinned_side(side1_contestant_id, best_side1):
        return None
    if not enumerate_pinned_side(side2_contestant_id, best_side2):
        return None

    out: dict[int, tuple[int | None, int | None]] = {}
    for i, ub in enumerate(ubs):
        r1 = int(best_side1[i])
        r2 = int(best_side2[i])
        out[ub.id] = (
            r1 if r1 <= n_players else None,
            r2 if r2 <= n_players else None,
        )
    return out


def compute_next_match_side_points_for_bracket(
    bracket: Bracket,
    next_stage_id: int,
    next_position: int,
    side1_contestant_id: int,
    side2_contestant_id: int,
    *,
    cap: int = MAX_UNDECIDED_MATCHUPS,
) -> dict[int, tuple[int | None, int | None]] | None:
    """Best achievable potential points per entry split by next-match outcome.

    In-memory only (no master DB writes). Same enumeration gate as
    :func:`compute_next_match_side_ranks_for_bracket`.
    """
    ctx = load_leaderboard_scoring_context(bracket)
    master = ctx.master
    if master is None:
        return None

    ubs = list(
        UserBracket.objects.filter(
            bracket=bracket,
            is_master=False,
            submitted_at__isnull=False,
        ).prefetch_related("matchup_set")
    )
    if not ubs:
        return {}

    ko_stages = [
        s
        for s in ctx.stages
        if s.stage_type == BracketStage.StageType.KNOCKOUT
    ]
    if not ko_stages:
        return None

    main_ko_stages = [
        s
        for s in ko_stages
        if not ctx.knockout_by_id[s.pk].is_third_place
    ]
    third_stage = next(
        (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_third_place),
        None,
    )
    final_stage = next(
        (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_final),
        None,
    )

    if main_ko_stages and not _first_knockout_fully_seeded(master, main_ko_stages[0]):
        return None

    tree = _build_master_tree(master, ko_stages)
    next_m_idx = _tree_matchup_index(tree, ko_stages, next_stage_id, next_position)
    if next_m_idx is None:
        return None

    pinned_probe = _copy_state(tree)
    _apply_winner(pinned_probe, next_m_idx, side1_contestant_id)
    if _count_undecided_matchups(pinned_probe) > cap:
        return None

    team_ids = _collect_team_ids(ubs, master, ko_stages, ctx)
    team_to_idx = {tid: i for i, tid in enumerate(sorted(team_ids))}
    if not team_to_idx:
        return None

    n_players = len(ubs)
    base = _base_group_scores(ubs, ctx)
    stage_pts = np.array(
        [
            float(ctx.knockout_by_id[s.pk].points_per_correct_pick)
            for s in main_ko_stages
        ],
        dtype=np.float64,
    )
    user_mask = _user_knockout_mask(ubs, main_ko_stages, team_to_idx)
    champ_pts = float(bracket.points_champion or 0)
    third_pts = float(bracket.points_third_place_winner or 0)
    user_champ = _user_winner_matrix(ubs, final_stage, team_to_idx, champ_pts)
    user_third = _user_winner_matrix(ubs, third_stage, team_to_idx, third_pts)

    final_m_idx = _final_matchup_index(tree, ko_stages, final_stage)
    third_m_idx = _final_matchup_index(tree, ko_stages, third_stage)

    n_stages = len(main_ko_stages)
    n_teams = len(team_to_idx)
    batch_size = _completion_batch_size(n_players, n_stages, n_teams)

    best_side1 = np.full(n_players, -1.0, dtype=np.float64)
    best_side2 = np.full(n_players, -1.0, dtype=np.float64)

    def enumerate_pinned_side(
        winner_id: int, best: np.ndarray
    ) -> bool:
        pinned = _copy_state(tree)
        _apply_winner(pinned, next_m_idx, winner_id)
        if _count_undecided_matchups(pinned) > cap:
            return False

        batch_masks: list[np.ndarray] = []
        batch_champ_bonus: list[np.ndarray] = []
        batch_third_bonus: list[np.ndarray] = []

        def flush_batch() -> None:
            nonlocal best
            if not batch_masks:
                return
            master_mask = np.stack(batch_masks, axis=0)
            weighted_user = user_mask * stage_pts[np.newaxis, :, np.newaxis]
            ko = np.einsum("pst,bst->bp", weighted_user, master_mask)
            totals = base[np.newaxis, :] + ko
            if champ_pts > 0 and batch_champ_bonus:
                totals += np.stack(batch_champ_bonus, axis=0)
            if third_pts > 0 and batch_third_bonus:
                totals += np.stack(batch_third_bonus, axis=0)
            best = np.maximum(best, np.max(totals, axis=0))
            batch_masks.clear()
            batch_champ_bonus.clear()
            batch_third_bonus.clear()

        def record_completion(state: _TreeState) -> None:
            batch_masks.append(
                _master_stage_mask(state, main_ko_stages, ko_stages, team_to_idx)
            )
            batch_champ_bonus.append(
                _winner_bonus(state, final_m_idx, user_champ, team_to_idx)
            )
            batch_third_bonus.append(
                _winner_bonus(state, third_m_idx, user_third, team_to_idx)
            )
            if len(batch_masks) >= batch_size:
                flush_batch()

        _enumerate_completions(tree, record_completion, state=pinned)
        flush_batch()
        return True

    if not enumerate_pinned_side(side1_contestant_id, best_side1):
        return None
    if not enumerate_pinned_side(side2_contestant_id, best_side2):
        return None

    out: dict[int, tuple[int | None, int | None]] = {}
    for i, ub in enumerate(ubs):
        p1 = float(best_side1[i])
        p2 = float(best_side2[i])
        out[ub.id] = (
            int(p1) if p1 >= 0 else None,
            int(p2) if p2 >= 0 else None,
        )
    return out


def _tree_matchup_index(
    tree: _TreeState,
    ko_stages: list,
    stage_id: int,
    position: int,
) -> int | None:
    stage_idx = next(
        (i for i, s in enumerate(ko_stages) if s.pk == stage_id), None
    )
    if stage_idx is None:
        return None
    for idx in tree.stage_matchup_indices[stage_idx]:
        if tree.matchups[idx].position == position:
            return idx
    return None


def _completion_batch_size(n_players: int, n_stages: int, n_teams: int) -> int:
    """Size completion batches from player count and mask width."""
    # master_mask (S×T float64) + totals/rank workspace (~5×N float64/int).
    per_completion = n_stages * n_teams * 8 + 40 * n_players
    per_completion = max(per_completion, 1)
    batch = MAX_BATCH_MEMORY_BYTES // per_completion
    return int(max(MIN_BATCH_SIZE, min(MAX_BATCH_SIZE, batch)))


def _competition_ranks_batch(totals: np.ndarray) -> np.ndarray:
    """
    Competition ranks for each completion row in ``totals`` (B, N).

    Ties share rank; O(B × N log N) via sort — not O(B × N²) pairwise compare.
    """
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


def _knockout_is_third_place(stage) -> bool:
    try:
        return KnockoutStage.objects.get(pk=stage.pk).is_third_place
    except KnockoutStage.DoesNotExist:
        return False


def _first_knockout_fully_seeded(master: UserBracket, first_ko) -> bool:
    if first_ko is None:
        return True
    has_group = master.bracket.stages.filter(
        stage_type=BracketStage.StageType.GROUP
    ).exists()
    if has_group:
        projected = projected_first_knockout_contestant_ids(master)
        if not projected:
            return False
    for m in master.matchup_set.filter(stage=first_ko).order_by("position"):
        if m.contestant1_id is None or m.contestant2_id is None:
            return False
    return True


def _build_master_tree(master: UserBracket, ko_stages: list) -> _TreeState:
    db_matchups = list(
        master.matchup_set.filter(stage__in=ko_stages).select_related(
            "stage",
            "source_a_matchup__stage",
            "source_b_matchup__stage",
        )
    )
    db_matchups.sort(key=lambda m: (m.stage.order, m.position))
    key_to_idx: dict[tuple[int, int], int] = {}
    mem: list[_MemMatchup] = []
    stage_indices: list[list[int]] = [[] for _ in ko_stages]
    stage_id_to_idx = {s.pk: i for i, s in enumerate(ko_stages)}

    for m in db_matchups:
        stage_idx = stage_id_to_idx[m.stage_id]
        mm = _MemMatchup(
            stage_idx=stage_idx,
            position=m.position,
            c1=m.contestant1_id,
            c2=m.contestant2_id,
            winner=m.winner_id,
            is_team_a=m.position % 2 == 1,
        )
        idx = len(mem)
        mem.append(mm)
        key_to_idx[(m.stage_id, m.position)] = idx
        stage_indices[stage_idx].append(idx)

    for m in db_matchups:
        idx = key_to_idx[(m.stage_id, m.position)]
        mm = mem[idx]
        ks = None
        try:
            ks = KnockoutStage.objects.get(pk=m.stage_id)
        except KnockoutStage.DoesNotExist:
            pass
        if ks and not ks.is_final and not ks.is_third_place:
            next_pos = (m.position + 1) // 2
            next_stages = [
                s
                for s in ko_stages
                if s.order > m.stage.order and not _knockout_is_third_place(s)
            ]
            if next_stages:
                next_idx = key_to_idx.get((next_stages[0].pk, next_pos))
                mm.next_idx = next_idx
        if m.source_a_matchup_id is not None and m.source_a_matchup is not None:
            src = key_to_idx.get(
                (m.source_a_matchup.stage_id, m.source_a_matchup.position)
            )
            if src is not None:
                mem[src].feeds.append((idx, "a", m.source_a_uses_winner))
        if m.source_b_matchup_id is not None and m.source_b_matchup is not None:
            src = key_to_idx.get(
                (m.source_b_matchup.stage_id, m.source_b_matchup.position)
            )
            if src is not None:
                mem[src].feeds.append((idx, "b", m.source_b_uses_winner))

    return _TreeState(matchups=mem, stage_matchup_indices=stage_indices)


def _count_undecided_matchups(tree: _TreeState) -> int:
    return sum(1 for m in tree.matchups if m.winner is None)


def _collect_team_ids(
    ubs: list[UserBracket],
    master: UserBracket,
    ko_stages: list,
    ctx,
) -> set[int]:
    ids: set[int] = set()
    for ub in ubs + [master]:
        for stage in ko_stages:
            ids |= contestants_credited_for_knockout_score(ub, stage)
        w = ub.get_final_matchup_winner()
        if w is not None:
            ids.add(w.id)
        tp = next(
            (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_third_place),
            None,
        )
        if tp is not None:
            m = ub.matchup_set.filter(stage=tp).first()
            if m:
                for cid in (m.winner_id, m.contestant1_id, m.contestant2_id):
                    if cid is not None:
                        ids.add(cid)
    for m in master.matchup_set.filter(stage__in=ko_stages):
        for cid in (m.contestant1_id, m.contestant2_id, m.winner_id):
            if cid is not None:
                ids.add(cid)
    return ids


def _base_group_scores(ubs: list[UserBracket], ctx) -> np.ndarray:
    scores = np.zeros(len(ubs), dtype=np.float64)
    for i, ub in enumerate(ubs):
        total = 0
        for stage in ctx.stages:
            if stage.stage_type != BracketStage.StageType.GROUP:
                continue
            stage_score = ub.calculate_stage_score(
                stage,
                master=ctx.master,
                knockout_stage=ctx.knockout_by_id.get(stage.pk),
                group_stage=ctx.group_by_id.get(stage.pk),
            )
            if stage_score is not None:
                total += stage_score
        scores[i] = total
    return scores


def _user_knockout_mask(
    ubs: list[UserBracket],
    main_ko_stages: list,
    team_to_idx: dict[int, int],
) -> np.ndarray:
    n = len(ubs)
    s = len(main_ko_stages)
    t = len(team_to_idx)
    mask = np.zeros((n, s, t), dtype=np.float64)
    for pi, ub in enumerate(ubs):
        for si, stage in enumerate(main_ko_stages):
            for tid in contestants_credited_for_knockout_score(ub, stage):
                ti = team_to_idx.get(tid)
                if ti is not None:
                    mask[pi, si, ti] = 1.0
    return mask


def _user_winner_matrix(
    ubs: list[UserBracket],
    stage,
    team_to_idx: dict[int, int],
    points: float,
) -> np.ndarray:
    n = len(ubs)
    t = len(team_to_idx)
    mat = np.zeros((n, t), dtype=np.float64)
    if stage is None or points <= 0:
        return mat
    for pi, ub in enumerate(ubs):
        if _knockout_is_third_place(stage):
            m = ub.matchup_set.filter(stage=stage).first()
            wid = m.winner_id if m else None
        else:
            w = ub.get_final_matchup_winner()
            wid = w.id if w else None
        if wid is not None:
            ti = team_to_idx.get(wid)
            if ti is not None:
                mat[pi, ti] = points
    return mat


def _final_matchup_index(
    tree: _TreeState,
    ko_stages: list,
    stage,
) -> int | None:
    if stage is None:
        return None
    stage_idx = next(i for i, s in enumerate(ko_stages) if s.pk == stage.pk)
    indices = tree.stage_matchup_indices[stage_idx]
    return indices[0] if indices else None


def _winner_bonus(
    state: _TreeState,
    m_idx: int | None,
    user_matrix: np.ndarray,
    team_to_idx: dict[int, int],
) -> np.ndarray:
    n = user_matrix.shape[0]
    if m_idx is None:
        return np.zeros(n, dtype=np.float64)
    wid = state.matchups[m_idx].winner
    if wid is None:
        return np.zeros(n, dtype=np.float64)
    ti = team_to_idx.get(wid)
    if ti is None:
        return np.zeros(n, dtype=np.float64)
    return user_matrix[:, ti].copy()


def _master_stage_mask(
    state: _TreeState,
    main_ko_stages: list,
    ko_stages: list,
    team_to_idx: dict[int, int],
) -> np.ndarray:
    stage_id_to_idx = {s.pk: i for i, s in enumerate(ko_stages)}
    s = len(main_ko_stages)
    t = len(team_to_idx)
    mask = np.zeros((s, t), dtype=np.float64)
    for si, stage in enumerate(main_ko_stages):
        ko_si = stage_id_to_idx[stage.pk]
        for m_idx in state.stage_matchup_indices[ko_si]:
            m = state.matchups[m_idx]
            for tid in (m.c1, m.c2):
                if tid is not None:
                    ti = team_to_idx.get(tid)
                    if ti is not None:
                        mask[si, ti] = 1.0
    return mask


def _copy_state(state: _TreeState) -> _TreeState:
    return _TreeState(
        matchups=[
            _MemMatchup(
                stage_idx=m.stage_idx,
                position=m.position,
                c1=m.c1,
                c2=m.c2,
                winner=m.winner,
                next_idx=m.next_idx,
                is_team_a=m.is_team_a,
                feeds=list(m.feeds),
            )
            for m in state.matchups
        ],
        stage_matchup_indices=[list(indices) for indices in state.stage_matchup_indices],
    )


def _apply_winner(state: _TreeState, m_idx: int, winner_id: int) -> None:
    m = state.matchups[m_idx]
    if m.c1 is None or m.c2 is None:
        return
    m.winner = winner_id
    loser_id = m.c2 if winner_id == m.c1 else m.c1

    if m.next_idx is not None:
        nxt = state.matchups[m.next_idx]
        if m.is_team_a:
            nxt.c1 = winner_id
        else:
            nxt.c2 = winner_id

    for feed_idx, slot, uses_winner in m.feeds:
        fm = state.matchups[feed_idx]
        val = winner_id if uses_winner else loser_id
        if slot == "a":
            fm.c1 = val
        else:
            fm.c2 = val


def _find_undecided(state: _TreeState) -> int | None:
    for i, m in enumerate(state.matchups):
        if m.winner is None and m.c1 is not None and m.c2 is not None:
            return i
    return None


def _enumerate_completions(
    tree: _TreeState,
    on_completion,
    *,
    state: _TreeState | None = None,
) -> None:
    state = state or _copy_state(tree)
    idx = _find_undecided(state)
    if idx is None:
        on_completion(state)
        return
    m = state.matchups[idx]
    for winner_id in (m.c1, m.c2):
        if winner_id is None:
            continue
        child = _copy_state(state)
        _apply_winner(child, idx, winner_id)
        _enumerate_completions(tree, on_completion, state=child)


def persist_potential_ranks_for_bracket(bracket: Bracket) -> None:
    """Compute and store potential ranks on all submitted entries."""
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
