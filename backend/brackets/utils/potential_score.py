"""
Maximum achievable score (Potential Points) for submitted brackets.

Potential points = stored current score + best marginal knockout/champion/third
gain from completing undecided master matchups forward from today's tree.
"""

from __future__ import annotations

from brackets.api.serializers import bracket_groups_preview
from brackets.models import Bracket, BracketStage, GroupStage, UserBracket
from brackets.utils.group_stage_config import group_stage_pick_requirements
from brackets.utils.leaderboard_scoring import (
    LEADERBOARD_SCORES_KEY,
    load_leaderboard_scoring_context,
)
from brackets.utils.potential_knockout import (
    max_potential_scores_backtrack,
    prepare_knockout_potential,
)


def _slots_per_group(gs: GroupStage) -> int:
    return gs.number_of_contestants // gs.number_of_groups


def master_knockout_has_results(master: UserBracket) -> bool:
    """True once any master knockout matchup has a recorded winner."""
    return master.matchup_set.filter(winner_id__isnull=False).exists()


def calculate_potential_score(
    user_bracket: UserBracket,
    *,
    master=None,
    main_ko_stages=None,
    groups_preview=None,
    knockout_by_id=None,
) -> int | None:
    """Upper bound on total points if the master finishes in the player's favor."""
    del main_ko_stages, knockout_by_id

    if user_bracket.is_master:
        return None

    if master is None:
        master = user_bracket.get_master_bracket()
    if master is None:
        return user_bracket.calculate_score()

    ctx = load_leaderboard_scoring_context(user_bracket.bracket)
    if ctx.master is None:
        return user_bracket.calculate_score()

    scores = compute_potential_scores_for_users(ctx, [user_bracket])
    if scores is not None:
        score = scores.get(user_bracket.id)
        if score is not None:
            return score

    return _fallback_potential_score(
        user_bracket,
        master,
        groups_preview=groups_preview,
    )


def compute_potential_scores_for_bracket(
    bracket: Bracket,
) -> dict[int, int | None] | None:
    """Return max achievable total score per submitted user bracket id."""
    ctx = load_leaderboard_scoring_context(bracket)
    ubs = list(
        UserBracket.objects.filter(
            bracket=bracket,
            is_master=False,
            submitted_at__isnull=False,
        ).prefetch_related("matchup_set")
    )
    return compute_potential_scores_for_users(ctx, ubs)


def compute_potential_scores_for_users(
    ctx,
    ubs: list[UserBracket],
) -> dict[int, int | None] | None:
    master = ctx.master
    if master is None:
        return {}
    if not ubs:
        return {}

    has_knockout = any(
        s.stage_type == BracketStage.StageType.KNOCKOUT for s in ctx.stages
    )
    if not has_knockout:
        return _group_only_scores(ubs, ctx, master)

    prepared = prepare_knockout_potential(ctx, ubs)
    if prepared is None:
        return None

    best = max_potential_scores_backtrack(prepared.tree, prepared.scoring)
    return {
        ub.id: int(best[i]) if best[i] >= 0 else None for i, ub in enumerate(ubs)
    }


def persist_potential_scores_for_bracket(bracket: Bracket) -> None:
    """Compute and store potential points on all submitted entries."""
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket

    qs = UserBracket.objects.filter(
        bracket=bracket,
        is_master=False,
        submitted_at__isnull=False,
    )
    if omit_leaderboard_potential_for_bracket(bracket):
        return

    scores = compute_potential_scores_for_bracket(bracket)
    if scores is None:
        return

    for ub in qs:
        score = scores.get(ub.id)
        if score is None:
            continue
        update_fields: list[str] = []
        if ub.leaderboard_potential != score:
            ub.leaderboard_potential = score
            update_fields.append("leaderboard_potential")
        meta = dict(ub.metadata) if isinstance(ub.metadata, dict) else {}
        cache = meta.get(LEADERBOARD_SCORES_KEY)
        if isinstance(cache, dict):
            cache = dict(cache)
            if cache.get("potential") != score:
                cache["potential"] = score
                meta[LEADERBOARD_SCORES_KEY] = cache
                ub.metadata = meta
                update_fields.append("metadata")
        if update_fields:
            ub.save(update_fields=update_fields)


def persist_all_potential_for_bracket(bracket: Bracket) -> None:
    """Materialize potential points, then potential rank (rank is best-effort)."""
    persist_potential_scores_for_bracket(bracket)
    from brackets.utils.potential_rank import persist_potential_ranks_for_bracket

    persist_potential_ranks_for_bracket(bracket)


def _group_only_scores(
    ubs: list[UserBracket],
    ctx,
    master: UserBracket,
) -> dict[int, int | None]:
    scores_arr = group_base_for_potential_scores(ubs, ctx, master)
    return {ub.id: int(scores_arr[i]) for i, ub in enumerate(ubs)}


def group_base_for_potential_scores(
    ubs: list[UserBracket],
    ctx,
    master: UserBracket,
):
    """Group component for potential (locked after knockout results exist)."""
    import numpy as np

    if master_knockout_has_results(master):
        return _base_group_scores(ubs, ctx)
    return _base_group_potential_scores(ubs, ctx)


def _base_group_scores(ubs: list[UserBracket], ctx) -> "np.ndarray":
    import numpy as np

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


def _base_group_potential_scores(ubs: list[UserBracket], ctx):
    import numpy as np

    groups_preview = bracket_groups_preview(ctx.master.bracket)
    scores = np.zeros(len(ubs), dtype=np.float64)
    for i, ub in enumerate(ubs):
        total = 0.0
        for stage in ctx.stages:
            if stage.stage_type != BracketStage.StageType.GROUP:
                continue
            gs = ctx.group_by_id.get(stage.pk)
            if gs is None:
                continue
            total += group_stage_potential(
                ub,
                ctx.master,
                gs,
                groups_preview=groups_preview,
            )
        scores[i] = total
    return scores


def _fallback_potential_score(
    user_bracket: UserBracket,
    master: UserBracket,
    *,
    groups_preview=None,
) -> int:
    """When knockout enumeration is unavailable, never inflate past current score."""
    current = user_bracket.calculate_score(master=master)
    current_int = current if current is not None else 0
    if master_knockout_has_results(master):
        return current_int

    total = 0
    for stage in user_bracket.bracket.stages.filter(
        stage_type=BracketStage.StageType.GROUP
    ):
        gs = GroupStage.objects.get(pk=stage.pk)
        total += group_stage_potential(
            user_bracket,
            master,
            gs,
            groups_preview=groups_preview,
        )
    if current_int > total:
        return current_int
    return total


def group_stage_potential(
    user_ub: UserBracket,
    master_ub: UserBracket,
    gs: GroupStage,
    *,
    groups_preview=None,
) -> int:
    user_gp = (user_ub.metadata or {}).get("group_positions") or {}
    master_gp = (master_ub.metadata or {}).get("group_positions") or {}
    if not isinstance(user_gp, dict):
        return 0

    _, third_count = group_stage_pick_requirements(gs)
    q = gs.contestants_qualifying_per_group
    slots = _slots_per_group(gs)
    total = 0

    if gs.points_per_exact_position > 0:
        preview = (
            groups_preview
            if groups_preview is not None
            else bracket_groups_preview(user_ub.bracket)
        )
        group_codes = [g["code"] for g in preview] or list(user_gp.keys())
        for code in group_codes:
            user_row = user_gp.get(code)
            if not isinstance(user_row, dict):
                user_row = {}
            master_row = master_gp.get(code)
            if not isinstance(master_row, dict):
                master_row = {}
            for pos in range(1, slots + 1):
                user_cid = UserBracket._position_contestant_id(user_row, pos)
                if user_cid is None:
                    continue
                master_cid = UserBracket._position_contestant_id(master_row, pos)
                if master_cid is None or master_cid == user_cid:
                    total += gs.points_per_exact_position

    if gs.points_per_advancer > 0:
        for code in user_gp:
            if not isinstance(user_gp.get(code), dict):
                continue
            user_adv = UserBracket._advancing_ids_from_positions(user_gp, code, q)
            master_row = master_gp.get(code)
            master_adv = (
                UserBracket._advancing_ids_from_positions(master_gp, code, q)
                if isinstance(master_row, dict)
                else set()
            )
            for cid in user_adv:
                if cid in master_adv:
                    total += gs.points_per_advancer
                elif _advancer_still_possible(master_gp, code, cid, q):
                    total += gs.points_per_advancer

        if third_count > 0:
            user_tp = (user_ub.metadata or {}).get("third_place_advancers") or []
            master_tp = (master_ub.metadata or {}).get("third_place_advancers") or []
            if isinstance(user_tp, list) and isinstance(master_tp, list):
                try:
                    master_tp_ids = {int(x) for x in master_tp if x is not None}
                except (TypeError, ValueError):
                    master_tp_ids = set()
                for cid in user_tp:
                    if cid is None:
                        continue
                    try:
                        cid_int = int(cid)
                    except (TypeError, ValueError):
                        continue
                    if cid_int in master_tp_ids:
                        total += gs.points_per_advancer
                    elif not master_tp_ids:
                        total += gs.points_per_advancer
                    elif len(master_tp_ids) < third_count:
                        total += gs.points_per_advancer

    return total


def _advancer_still_possible(
    master_gp: dict, group_code: str, contestant_id: int, qualifying: int
) -> bool:
    row = master_gp.get(group_code)
    if not isinstance(row, dict):
        return True
    for pos in range(1, qualifying + 1):
        master_cid = UserBracket._position_contestant_id(row, pos)
        if master_cid is None:
            return True
    advancing = UserBracket._advancing_ids_from_positions(
        master_gp, group_code, qualifying
    )
    return contestant_id in advancing
