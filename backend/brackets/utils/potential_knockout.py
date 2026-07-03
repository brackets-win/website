"""
Shared master-knockout tree and marginal scoring for potential points / rank.

Potential points and potential rank each have their own module; this file holds
the tree build, propagation, and per-completion score vectors they both need.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from brackets.models import BracketStage, KnockoutStage, UserBracket
from brackets.utils.sync_group_knockout import (
    contestants_credited_for_knockout_score,
    projected_first_knockout_contestant_ids,
)


@dataclass
class MemMatchup:
    stage_idx: int
    position: int
    c1: int | None = None
    c2: int | None = None
    winner: int | None = None
    next_idx: int | None = None
    is_team_a: bool = False
    feeds: list[tuple[int, str, bool]] = field(default_factory=list)


@dataclass
class TreeState:
    matchups: list[MemMatchup]
    stage_matchup_indices: list[list[int]]


@dataclass
class KnockoutScoringParams:
    current_totals: np.ndarray
    current_ko_bonus: np.ndarray
    user_mask: np.ndarray
    stage_pts: np.ndarray
    user_champ: np.ndarray
    user_third: np.ndarray
    final_m_idx: int | None
    third_m_idx: int | None
    team_to_idx: dict[int, int]
    main_ko_stages: list
    ko_stages: list


@dataclass
class KnockoutPotentialContext:
    """Prepared tree + scoring arrays for one bracket snapshot."""

    tree: TreeState
    scoring: KnockoutScoringParams
    branchable: int
    ubs: list[UserBracket]
    champ_pts: float
    third_pts: float


UndoChange = tuple[int, str, int | None]


def knockout_is_third_place(stage) -> bool:
    try:
        return KnockoutStage.objects.get(pk=stage.pk).is_third_place
    except KnockoutStage.DoesNotExist:
        return False


def first_knockout_fully_seeded(master: UserBracket, first_ko) -> bool:
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


def build_master_tree(master: UserBracket, ko_stages: list) -> TreeState:
    db_matchups = list(
        master.matchup_set.filter(stage__in=ko_stages).select_related(
            "stage",
            "source_a_matchup__stage",
            "source_b_matchup__stage",
        )
    )
    db_matchups.sort(key=lambda m: (m.stage.order, m.position))
    key_to_idx: dict[tuple[int, int], int] = {}
    mem: list[MemMatchup] = []
    stage_indices: list[list[int]] = [[] for _ in ko_stages]
    stage_id_to_idx = {s.pk: i for i, s in enumerate(ko_stages)}

    for m in db_matchups:
        stage_idx = stage_id_to_idx[m.stage_id]
        mm = MemMatchup(
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
                if s.order > m.stage.order and not knockout_is_third_place(s)
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

    return TreeState(matchups=mem, stage_matchup_indices=stage_indices)


def count_branchable_undecided_matchups(tree: TreeState) -> int:
    """Undecided matchups with both teams — the only nodes we branch on."""
    return sum(
        1
        for m in tree.matchups
        if m.winner is None and m.c1 is not None and m.c2 is not None
    )


def collect_team_ids(
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


def current_totals_for_users(ubs: list[UserBracket], ctx) -> np.ndarray:
    """Materialized total score per entry — same as the leaderboard Score column."""
    master = ctx.master
    scores = np.zeros(len(ubs), dtype=np.float64)
    for i, ub in enumerate(ubs):
        if ub.leaderboard_score is not None:
            scores[i] = float(ub.leaderboard_score)
            continue
        total = 0.0
        for stage in ctx.stages:
            stage_score = ub.calculate_stage_score(
                stage,
                master=master,
                knockout_stage=ctx.knockout_by_id.get(stage.pk),
                group_stage=ctx.group_by_id.get(stage.pk),
            )
            if stage_score is not None:
                total += stage_score
        champion = ub.calculate_champion_score(master=master)
        if champion is not None:
            total += champion
        scores[i] = total
    return scores


def prepare_knockout_potential(
    ctx,
    ubs: list[UserBracket],
) -> KnockoutPotentialContext | None:
    """
    Build tree + scoring arrays for knockout potential.

    Returns ``None`` when the first knockout round is not fully seeded.
    """
    master = ctx.master
    if master is None or not ubs:
        return None

    ko_stages = [
        s for s in ctx.stages if s.stage_type == BracketStage.StageType.KNOCKOUT
    ]
    if not ko_stages:
        return None

    main_ko_stages = [
        s for s in ko_stages if not ctx.knockout_by_id[s.pk].is_third_place
    ]
    third_stage = next(
        (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_third_place),
        None,
    )
    final_stage = next(
        (s for s in ko_stages if ctx.knockout_by_id[s.pk].is_final),
        None,
    )

    if main_ko_stages and not first_knockout_fully_seeded(master, main_ko_stages[0]):
        return None

    tree = build_master_tree(master, ko_stages)
    branchable = count_branchable_undecided_matchups(tree)

    team_ids = collect_team_ids(ubs, master, ko_stages, ctx)
    team_to_idx = {tid: i for i, tid in enumerate(sorted(team_ids))}
    if not team_to_idx:
        return None

    stage_pts = np.array(
        [
            float(ctx.knockout_by_id[s.pk].points_per_correct_pick)
            for s in main_ko_stages
        ],
        dtype=np.float64,
    )
    user_mask = user_knockout_mask(ubs, main_ko_stages, team_to_idx)
    bracket = master.bracket
    champ_pts = float(bracket.points_champion or 0)
    third_pts = float(bracket.points_third_place_winner or 0)
    user_champ = user_winner_matrix(ubs, final_stage, team_to_idx, champ_pts)
    user_third = user_winner_matrix(ubs, third_stage, team_to_idx, third_pts)
    final_m_idx = final_matchup_index(tree, ko_stages, final_stage)
    third_m_idx = final_matchup_index(tree, ko_stages, third_stage)

    current_state = copy_tree_state(tree)
    current_ko_bonus = marginal_ko_bonus(
        current_state,
        user_mask=user_mask,
        stage_pts=stage_pts,
        user_champ=user_champ,
        user_third=user_third,
        final_m_idx=final_m_idx,
        third_m_idx=third_m_idx,
        team_to_idx=team_to_idx,
        main_ko_stages=main_ko_stages,
        ko_stages=ko_stages,
    )

    scoring = KnockoutScoringParams(
        current_totals=current_totals_for_users(ubs, ctx),
        current_ko_bonus=current_ko_bonus,
        user_mask=user_mask,
        stage_pts=stage_pts,
        user_champ=user_champ,
        user_third=user_third,
        final_m_idx=final_m_idx,
        third_m_idx=third_m_idx,
        team_to_idx=team_to_idx,
        main_ko_stages=main_ko_stages,
        ko_stages=ko_stages,
    )
    return KnockoutPotentialContext(
        tree=tree,
        scoring=scoring,
        branchable=branchable,
        ubs=ubs,
        champ_pts=champ_pts,
        third_pts=third_pts,
    )


def user_knockout_mask(
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


def user_winner_matrix(
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
        if knockout_is_third_place(stage):
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


def final_matchup_index(tree: TreeState, ko_stages: list, stage) -> int | None:
    if stage is None:
        return None
    stage_idx = next(i for i, s in enumerate(ko_stages) if s.pk == stage.pk)
    indices = tree.stage_matchup_indices[stage_idx]
    return indices[0] if indices else None


def winner_bonus(
    state: TreeState,
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


def master_stage_mask(
    state: TreeState,
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


def marginal_ko_bonus(
    state: TreeState,
    *,
    user_mask: np.ndarray,
    stage_pts: np.ndarray,
    user_champ: np.ndarray,
    user_third: np.ndarray,
    final_m_idx: int | None,
    third_m_idx: int | None,
    team_to_idx: dict[int, int],
    main_ko_stages: list,
    ko_stages: list,
) -> np.ndarray:
    master_mask = master_stage_mask(state, main_ko_stages, ko_stages, team_to_idx)
    weighted_user = user_mask * stage_pts[np.newaxis, :, np.newaxis]
    totals = np.einsum("bst,st->b", weighted_user, master_mask)
    if final_m_idx is not None:
        totals += winner_bonus(state, final_m_idx, user_champ, team_to_idx)
    if third_m_idx is not None:
        totals += winner_bonus(state, third_m_idx, user_third, team_to_idx)
    return totals


def completion_totals_vector(
    state: TreeState, scoring: KnockoutScoringParams
) -> np.ndarray:
    master_mask = master_stage_mask(
        state,
        scoring.main_ko_stages,
        scoring.ko_stages,
        scoring.team_to_idx,
    )
    weighted_user = scoring.user_mask * scoring.stage_pts[:, np.newaxis]
    completion_marginal = np.einsum("bst,st->b", weighted_user, master_mask)
    if scoring.final_m_idx is not None:
        completion_marginal = completion_marginal + winner_bonus(
            state,
            scoring.final_m_idx,
            scoring.user_champ,
            scoring.team_to_idx,
        )
    if scoring.third_m_idx is not None:
        completion_marginal = completion_marginal + winner_bonus(
            state,
            scoring.third_m_idx,
            scoring.user_third,
            scoring.team_to_idx,
        )
    return scoring.current_totals + completion_marginal - scoring.current_ko_bonus


MAX_BATCH_SIZE = 4096
MIN_BATCH_SIZE = 32
MAX_BATCH_MEMORY_BYTES = 64 * 1024 * 1024


def completion_batch_size(n_players: int, n_stages: int, n_teams: int) -> int:
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


def enumerate_potential_outcomes(
    tree: TreeState,
    scoring: KnockoutScoringParams,
    *,
    n_players: int,
    champ_pts: float,
    third_pts: float,
    compute_ranks: bool,
) -> tuple[np.ndarray, np.ndarray | None]:
    """
    Walk all master completions once (in-place undo, no per-branch tree copies).

    Returns ``(best_scores, best_ranks)``. ``best_ranks`` is ``None`` when
    ``compute_ranks`` is false.
    """
    n_stages = len(scoring.main_ko_stages)
    n_teams = len(scoring.team_to_idx)
    batch_size = completion_batch_size(n_players, n_stages, n_teams)

    best_scores = np.full(n_players, -1.0, dtype=np.float64)
    best_ranks = (
        np.full(n_players, n_players + 1, dtype=np.int32) if compute_ranks else None
    )
    batch_masks: list[np.ndarray] = []
    batch_champ_bonus: list[np.ndarray] = []
    batch_third_bonus: list[np.ndarray] = []

    def flush_batch() -> None:
        nonlocal best_scores, best_ranks
        if not batch_masks:
            return
        master_mask = np.stack(batch_masks, axis=0)
        weighted_user = scoring.user_mask * scoring.stage_pts[np.newaxis, :, np.newaxis]
        completion_marginal = np.einsum("pst,bst->bp", weighted_user, master_mask)
        if champ_pts > 0 and batch_champ_bonus:
            completion_marginal = completion_marginal + np.stack(batch_champ_bonus, axis=0)
        if third_pts > 0 and batch_third_bonus:
            completion_marginal = completion_marginal + np.stack(batch_third_bonus, axis=0)
        totals = (
            scoring.current_totals[np.newaxis, :]
            + completion_marginal
            - scoring.current_ko_bonus
        )
        best_scores = np.maximum(best_scores, np.max(totals, axis=0))
        if compute_ranks and best_ranks is not None:
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

    state = copy_tree_state(tree)

    def walk() -> None:
        idx = find_undecided(state)
        if idx is None:
            record_completion(state)
            return
        m = state.matchups[idx]
        for winner_id in (m.c1, m.c2):
            if winner_id is None:
                continue
            changes = apply_winner_with_undo(state, idx, winner_id)
            walk()
            restore_undo(state, changes)

    walk()
    flush_batch()
    return best_scores, best_ranks


def max_potential_scores_batch(
    tree: TreeState,
    scoring: KnockoutScoringParams,
    *,
    champ_pts: float,
    third_pts: float,
) -> np.ndarray:
    """Best total score — vectorized batches over master completions."""
    n_players = len(scoring.current_totals)
    best_scores, _ = enumerate_potential_outcomes(
        tree,
        scoring,
        n_players=n_players,
        champ_pts=champ_pts,
        third_pts=third_pts,
        compute_ranks=False,
    )
    return best_scores


def max_potential_scores_backtrack(
    tree: TreeState, scoring: KnockoutScoringParams
) -> np.ndarray:
    """Best total score — in-place backtracking (small pools / tests only)."""
    best_scores = np.full(len(scoring.current_totals), -1.0, dtype=np.float64)
    state = copy_tree_state(tree)

    def search() -> None:
        nonlocal best_scores
        idx = find_undecided(state)
        if idx is None:
            np.maximum(
                best_scores, completion_totals_vector(state, scoring), out=best_scores
            )
            return
        m = state.matchups[idx]
        for winner_id in (m.c1, m.c2):
            if winner_id is None:
                continue
            changes = apply_winner_with_undo(state, idx, winner_id)
            search()
            restore_undo(state, changes)

    search()
    return best_scores


def copy_tree_state(state: TreeState) -> TreeState:
    return TreeState(
        matchups=[
            MemMatchup(
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


def apply_winner_with_undo(
    state: TreeState, m_idx: int, winner_id: int
) -> list[UndoChange]:
    changes: list[UndoChange] = []
    m = state.matchups[m_idx]
    if m.c1 is None or m.c2 is None:
        return changes

    def record(idx: int, attr: str) -> None:
        changes.append((idx, attr, getattr(state.matchups[idx], attr)))

    record(m_idx, "winner")
    m.winner = winner_id
    loser_id = m.c2 if winner_id == m.c1 else m.c1

    if m.next_idx is not None:
        nxt = state.matchups[m.next_idx]
        if m.is_team_a:
            record(m.next_idx, "c1")
            nxt.c1 = winner_id
        else:
            record(m.next_idx, "c2")
            nxt.c2 = winner_id

    for feed_idx, slot, uses_winner in m.feeds:
        fm = state.matchups[feed_idx]
        val = winner_id if uses_winner else loser_id
        if slot == "a":
            record(feed_idx, "c1")
            fm.c1 = val
        else:
            record(feed_idx, "c2")
            fm.c2 = val
    return changes


def restore_undo(state: TreeState, changes: list[UndoChange]) -> None:
    for idx, attr, val in reversed(changes):
        setattr(state.matchups[idx], attr, val)


def apply_winner(state: TreeState, m_idx: int, winner_id: int) -> None:
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


def find_undecided(state: TreeState) -> int | None:
    for i, m in enumerate(state.matchups):
        if m.winner is None and m.c1 is not None and m.c2 is not None:
            return i
    return None


def enumerate_completions(tree: TreeState, on_completion) -> None:
    """Depth-first over all master completions (in-place, for tests)."""

    state = copy_tree_state(tree)

    def walk() -> None:
        idx = find_undecided(state)
        if idx is None:
            on_completion(state)
            return
        m = state.matchups[idx]
        for winner_id in (m.c1, m.c2):
            if winner_id is None:
                continue
            changes = apply_winner_with_undo(state, idx, winner_id)
            walk()
            restore_undo(state, changes)

    walk()
