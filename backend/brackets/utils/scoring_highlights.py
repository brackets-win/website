"""Which user picks have earned points vs the master bracket (for UI highlighting)."""

from __future__ import annotations

from brackets.models import BracketStage, GroupStage, KnockoutStage, UserBracket
from brackets.utils.sync_group_knockout import (
    _get_first_knockout_stage,
    contestants_in_stage_for_scoring,
)


def scoring_highlights_for_user_bracket(ub: UserBracket) -> dict:
    master = ub.get_master_bracket()
    if master is None or ub.is_master:
        return {}

    group_positions: dict[str, dict[str, bool]] = {}
    group_advancers: list[int] = []
    knockout_contestants: list[dict[str, int]] = []
    champion_contestant_id: int | None = None
    third_place_contestant_id: int | None = None

    for stage in ub.bracket.stages.filter(stage_type=BracketStage.StageType.GROUP):
        gs = GroupStage.objects.get(pk=stage.pk)
        user_gp = (ub.metadata or {}).get("group_positions") or {}
        master_gp = (master.metadata or {}).get("group_positions") or {}
        if not isinstance(user_gp, dict) or not isinstance(master_gp, dict):
            continue

        if gs.points_per_exact_position > 0:
            for code, user_row in user_gp.items():
                if not isinstance(user_row, dict):
                    continue
                master_row = master_gp.get(code)
                if not isinstance(master_row, dict):
                    continue
                row_h: dict[str, bool] = {}
                for pos, user_cid in user_row.items():
                    if user_cid is None:
                        continue
                    try:
                        user_id = int(user_cid)
                    except (TypeError, ValueError):
                        continue
                    master_cid = UserBracket._position_contestant_id(master_row, pos)
                    if master_cid is not None and user_id == master_cid:
                        row_h[str(pos)] = True
                if row_h:
                    group_positions[code] = row_h

        if gs.points_per_advancer > 0:
            q = gs.contestants_qualifying_per_group
            for code in user_gp:
                if not isinstance(user_gp.get(code), dict):
                    continue
                user_ids = UserBracket._advancing_ids_from_positions(
                    user_gp, code, q
                )
                master_ids = UserBracket._advancing_ids_from_positions(
                    master_gp, code, q
                )
                group_advancers.extend(sorted(user_ids & master_ids))

            user_tp = (ub.metadata or {}).get("third_place_advancers") or []
            master_tp = (master.metadata or {}).get("third_place_advancers") or []
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
                        group_advancers.append(cid_int)

    group_advancers = sorted(set(group_advancers))

    # Knockout-only brackets seed the first round, so those slots earn no
    # points and must not be highlighted. Group → knockout brackets keep it:
    # the first round reflects who the user picked to advance from groups.
    has_group_stage = ub.bracket.stages.filter(
        stage_type=BracketStage.StageType.GROUP
    ).exists()
    first_ko = None if has_group_stage else _get_first_knockout_stage(ub.bracket)

    for stage in ub.bracket.stages.filter(
        stage_type=BracketStage.StageType.KNOCKOUT
    ).order_by("order"):
        ks = KnockoutStage.objects.filter(pk=stage.pk).first()
        if ks and ks.is_third_place:
            continue
        if first_ko is not None and stage.pk == first_ko.pk:
            continue
        user_ids = contestants_in_stage_for_scoring(ub, stage)
        master_ids = contestants_in_stage_for_scoring(master, stage)
        for cid in sorted(user_ids & master_ids):
            knockout_contestants.append(
                {"stage_id": stage.id, "contestant_id": cid}
            )

    if ub.calculate_champion_score() > 0:
        champ = ub.get_final_matchup_winner()
        if champ is not None:
            champion_contestant_id = champ.id

    for stage in ub.bracket.stages.filter(
        stage_type=BracketStage.StageType.KNOCKOUT
    ):
        ks = KnockoutStage.objects.filter(pk=stage.pk).first()
        if ks and ks.is_third_place:
            if ub._calculate_third_place_stage_score(master, stage) > 0:
                user_m = ub.matchup_set.filter(stage=stage).first()
                if user_m and user_m.winner_id:
                    third_place_contestant_id = user_m.winner_id
            break

    return {
        "group_positions": group_positions,
        "group_advancers": group_advancers,
        "knockout_contestants": knockout_contestants,
        "champion_contestant_id": champion_contestant_id,
        "third_place_contestant_id": third_place_contestant_id,
    }
