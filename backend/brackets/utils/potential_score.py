"""
Maximum achievable score for a user bracket vs a (possibly partial) master bracket.

Uses backward reachability on knockout tree positions — not enumeration of all
master completions.
"""

from __future__ import annotations

from brackets.api.serializers import bracket_groups_preview
from brackets.models import BracketStage, GroupStage, KnockoutStage, Matchup, UserBracket
from brackets.utils.group_stage_config import group_stage_pick_requirements
from brackets.utils.sync_group_knockout import contestants_in_stage_for_scoring


def _slots_per_group(gs: GroupStage) -> int:
    """Finish positions per group (e.g. 4 for World Cup 12×4)."""
    return gs.number_of_contestants // gs.number_of_groups


def calculate_potential_score(user_bracket: UserBracket, *, master=None) -> int | None:
    """Upper bound on total points if every remaining outcome goes the player's way."""
    if user_bracket.is_master:
        return None

    if master is None:
        master = user_bracket.get_master_bracket()
    if master is None:
        return user_bracket.calculate_score()

    total = 0
    bracket = user_bracket.bracket

    for stage in bracket.stages.filter(stage_type=BracketStage.StageType.GROUP):
        gs = GroupStage.objects.get(pk=stage.pk)
        total += _group_stage_potential(user_bracket, master, gs)

    for stage in _main_knockout_stages(bracket):
        ks = KnockoutStage.objects.get(pk=stage.pk)
        pts = ks.points_per_correct_pick
        user_ids = contestants_in_stage_for_scoring(user_bracket, stage)
        master_ids = contestants_in_stage_for_scoring(master, stage)
        for team_id in user_ids:
            if team_id in master_ids:
                total += pts
            elif _team_can_reach_knockout_stage(
                user_bracket, master, team_id, stage
            ):
                total += pts

    total += _champion_potential(user_bracket, master)
    total += _third_place_potential(user_bracket, master)
    return total


def _main_knockout_stages(bracket) -> list:
    out = []
    for stage in bracket.stages.filter(
        stage_type=BracketStage.StageType.KNOCKOUT
    ).order_by("order"):
        ks = KnockoutStage.objects.filter(pk=stage.pk).first()
        if ks and ks.is_third_place:
            continue
        out.append(stage)
    return out


def _knockout_stage_index(bracket, stage) -> int:
    stages = _main_knockout_stages(bracket)
    for i, s in enumerate(stages):
        if s.pk == stage.pk:
            return i
    return -1


def _matchup_at(ub: UserBracket, stage, position: int) -> Matchup | None:
    return (
        Matchup.objects.filter(
            user_bracket=ub, stage=stage, position=position
        )
        .select_related("contestant1", "contestant2", "winner")
        .first()
    )


def _feeder_position(position: int, *, team_is_contestant1: bool) -> int:
    return 2 * position - 1 if team_is_contestant1 else 2 * position


def _team_can_still_win_matchup(team_id: int, matchup: Matchup | None) -> bool:
    if matchup is None:
        return False
    if matchup.winner_id is not None:
        return matchup.winner_id == team_id
    # Undecided — master lineup may still change; user side can still win.
    return True


def _team_can_reach_knockout_stage(
    user_ub: UserBracket,
    master_ub: UserBracket,
    team_id: int,
    target_stage,
) -> bool:
    user_matchup = None
    for m in user_ub.matchup_set.filter(stage=target_stage):
        if team_id == m.contestant1_id:
            user_matchup = m
            team_is_c1 = True
            break
        if team_id == m.contestant2_id:
            user_matchup = m
            team_is_c1 = False
            break
    if user_matchup is None:
        return False

    bracket = user_ub.bracket
    ko_stages = _main_knockout_stages(bracket)
    if not ko_stages:
        return False

    stage = target_stage
    position = user_matchup.position
    team_is_c1 = team_id == user_matchup.contestant1_id

    while True:
        master_m = _matchup_at(master_ub, stage, position)
        if not _team_can_still_win_matchup(team_id, master_m):
            return False
        if stage.pk == ko_stages[0].pk:
            return True

        idx = _knockout_stage_index(bracket, stage)
        if idx <= 0:
            return False
        prev_stage = ko_stages[idx - 1]
        position = _feeder_position(position, team_is_contestant1=team_is_c1)
        user_m = _matchup_at(user_ub, prev_stage, position)
        if user_m is None or team_id not in (user_m.contestant1_id, user_m.contestant2_id):
            return False
        team_is_c1 = team_id == user_m.contestant1_id
        stage = prev_stage


def _group_stage_potential(
    user_ub: UserBracket, master_ub: UserBracket, gs: GroupStage
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
        preview = bracket_groups_preview(user_ub.bracket)
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
            user_adv = UserBracket._advancing_ids_from_positions(
                user_gp, code, q
            )
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


def _champion_potential(user_ub: UserBracket, master_ub: UserBracket) -> int:
    pts = user_ub.bracket.points_champion
    if pts <= 0:
        return 0

    final_stage = KnockoutStage.objects.filter(
        bracket=user_ub.bracket, is_final=True
    ).first()
    if not final_stage:
        return 0

    user_final = user_ub.matchup_set.filter(stage=final_stage).first()
    master_final = master_ub.matchup_set.filter(stage=final_stage).first()
    if not user_final:
        return 0

    if master_final and master_final.winner_id is not None:
        if user_final.winner_id is None:
            return 0
        return pts if master_final.winner_id == user_final.winner_id else 0

    if user_final.winner_id is not None:
        team_id = user_final.winner_id
        if _team_can_reach_knockout_stage(
            user_ub, master_ub, team_id, final_stage
        ) and _team_can_still_win_matchup(team_id, master_final):
            return pts
        return 0

    if user_final.contestant1_id and user_final.contestant2_id:
        return pts
    return 0


def _third_place_potential(user_ub: UserBracket, master_ub: UserBracket) -> int:
    pts = user_ub.bracket.points_third_place_winner
    if pts <= 0:
        return 0

    tp_stage = KnockoutStage.objects.filter(
        bracket=user_ub.bracket, is_third_place=True
    ).first()
    if not tp_stage:
        return 0

    user_m = user_ub.matchup_set.filter(stage=tp_stage).first()
    master_m = master_ub.matchup_set.filter(stage=tp_stage).first()
    if not user_m:
        return 0

    if master_m and master_m.winner_id is not None:
        if user_m.winner_id is None:
            return 0
        return pts if master_m.winner_id == user_m.winner_id else 0

    if user_m.winner_id is not None:
        team_id = user_m.winner_id
        if master_m:
            c1, c2 = master_m.contestant1_id, master_m.contestant2_id
            if c1 is None and c2 is None:
                return pts
            if team_id in (c1, c2):
                return pts
        return pts

    if user_m.contestant1_id and user_m.contestant2_id:
        return pts
    return 0
