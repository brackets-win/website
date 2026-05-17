"""Whether a user bracket has all required picks before submit."""

from __future__ import annotations

from brackets.models import KnockoutStage, UserBracket


def user_bracket_is_complete(ub: UserBracket) -> tuple[bool, str | None]:
    from brackets.api.serializers import bracket_groups_preview

    bracket = ub.bracket
    preview = bracket_groups_preview(bracket)
    meta = ub.metadata if isinstance(ub.metadata, dict) else {}

    if preview:
        gp = meta.get("group_positions") or {}
        is_wc = (bracket.metadata or {}).get("tournament_type") == "world_cup_2026"
        slots_required = 3 if is_wc else 2
        slot_keys = ["1", "2", "3"][:slots_required]

        for group in preview:
            code = group["code"]
            slots = gp.get(code) or {}
            for key in slot_keys:
                val = slots.get(key)
                if val is None:
                    val = slots.get(int(key)) if isinstance(slots, dict) else None
                if val is None:
                    return False, f"Complete group {code} picks first"

        if is_wc:
            tp = meta.get("third_place_advancers") or []
            if len(tp) < 8:
                return False, "Select 8 third-place teams"

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

    return True, None
