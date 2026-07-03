"""
Maximum achievable score for a user bracket vs a (possibly partial) master bracket.

Knockout potential is the best total score across all valid completions of the
master knockout tree (same engine as potential rank). Group-stage potential still
credits finish/advancer picks the master has not ruled out.
"""

from __future__ import annotations

from brackets.api.serializers import bracket_groups_preview
from brackets.models import BracketStage, GroupStage, UserBracket
from brackets.utils.group_stage_config import group_stage_pick_requirements


def _slots_per_group(gs: GroupStage) -> int:
    """Finish positions per group (e.g. 4 for World Cup 12×4)."""
    return gs.number_of_contestants // gs.number_of_groups


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

    from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
    from brackets.utils.potential_rank import (
        MAX_UNDECIDED_MATCHUPS,
        _enumerate_potential_outcomes_for_users,
    )

    ctx = load_leaderboard_scoring_context(user_bracket.bracket)
    if ctx.master is None:
        return user_bracket.calculate_score()

    outcomes = _enumerate_potential_outcomes_for_users(
        ctx,
        [user_bracket],
        cap=MAX_UNDECIDED_MATCHUPS,
    )
    if outcomes is not None:
        score = outcomes[0].get(user_bracket.id)
        if score is not None:
            return score

    return _fallback_potential_score(
        user_bracket,
        master,
        groups_preview=groups_preview,
    )


def _fallback_potential_score(
    user_bracket: UserBracket,
    master: UserBracket,
    *,
    groups_preview=None,
) -> int:
    """When knockout enumeration is unavailable, use group potential + current score."""
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
    current = user_bracket.calculate_score(master=master)
    if current is not None and current > total:
        return current
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
