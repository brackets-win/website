"""Whether a user bracket has all required picks before submit."""

from __future__ import annotations

from brackets.models import KnockoutStage, UserBracket
from brackets.utils.group_stage_config import (
    get_group_stage,
    group_stage_pick_requirements,
)


def user_bracket_is_complete(ub: UserBracket) -> tuple[bool, str | None]:
    from brackets.api.serializers import bracket_groups_preview

    bracket = ub.bracket
    preview = bracket_groups_preview(bracket)
    meta = ub.metadata if isinstance(ub.metadata, dict) else {}

    if preview:
        gs = get_group_stage(bracket)
        if gs is None:
            return False, "Bracket has no group stage"

        ranks_required, third_count = group_stage_pick_requirements(gs)
        slot_keys = [str(i) for i in range(1, ranks_required + 1)]

        gp = meta.get("group_positions") or {}
        for group in preview:
            code = group["code"]
            slots = gp.get(code) or {}
            for key in slot_keys:
                val = slots.get(key)
                if val is None:
                    val = slots.get(int(key)) if isinstance(slots, dict) else None
                if val is None:
                    return False, f"Complete group {code} picks first"

        if third_count > 0:
            tp = meta.get("third_place_advancers") or []
            if len(tp) < third_count:
                return False, f"Select {third_count} third-place teams"

    for m in ub.matchup_set.select_related("stage").all():
        if m.contestant1_id and m.contestant2_id and m.winner_id is None:
            return False, "Pick a winner for every available matchup"

    final_ks = KnockoutStage.objects.filter(bracket=bracket, is_final=True).first()
    if final_ks:
        final_matchup = (
            ub.matchup_set.filter(stage_id=final_ks.pk).order_by("position").first()
        )
        if final_matchup and final_matchup.winner_id is None:
            if final_matchup.contestant1_id and final_matchup.contestant2_id:
                return False, "Pick a champion"

    third_ks = KnockoutStage.objects.filter(bracket=bracket, is_third_place=True).first()
    if third_ks:
        third_matchup = (
            ub.matchup_set.filter(stage_id=third_ks.pk).order_by("position").first()
        )
        if third_matchup and third_matchup.winner_id is None:
            if third_matchup.contestant1_id and third_matchup.contestant2_id:
                return False, "Pick a third-place winner"

    return True, None
