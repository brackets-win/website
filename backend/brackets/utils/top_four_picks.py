"""Final-four picks from a user bracket for leaderboard display."""

from __future__ import annotations

from typing import Any

from brackets.models import BracketContestant, BracketStage, KnockoutStage, UserBracket
from brackets.utils.knockout_tree import _semifinal_stage_before_final


def _pick_payload(bc: BracketContestant | None) -> dict[str, Any] | None:
    if bc is None:
        return None
    name = bc.name_override or (
        bc.contestant.name if bc.contestant else f"Contestant {bc.id}"
    )
    img: str | None = None
    c = bc.contestant
    if c:
        if getattr(c, "photo", None) and c.photo:
            img = c.photo.url
        elif c.image_url:
            img = c.image_url
    return {
        "bracket_contestant_id": bc.id,
        "image_url": img,
        "display_name": name,
    }


def top_four_bracket_contestants(ub: UserBracket) -> list[BracketContestant | None]:
    """
    Champion, runner-up, then either third-place winner & loser or two
    semifinal losers (left to right).
    """
    bracket = ub.bracket
    final_ks = KnockoutStage.objects.filter(bracket=bracket, is_final=True).first()
    if not final_ks:
        return [None, None, None, None]

    final_stage = BracketStage.objects.get(pk=final_ks.pk)
    final_m = ub.matchup_set.filter(stage=final_stage).first()
    champion = final_m.winner if final_m else None
    runner_up = final_m.get_loser() if final_m and final_m.winner_id else None

    if bracket.has_third_place_match:
        third_ks = KnockoutStage.objects.filter(
            bracket=bracket, is_third_place=True
        ).first()
        if third_ks:
            tp_m = ub.matchup_set.filter(stage_id=third_ks.pk).first()
            third_w = tp_m.winner if tp_m else None
            third_l = tp_m.get_loser() if tp_m and tp_m.winner_id else None
            return [champion, runner_up, third_w, third_l]

    sf_stage = _semifinal_stage_before_final(bracket, final_stage)
    if not sf_stage:
        return [champion, runner_up, None, None]

    semi_losers: list[BracketContestant | None] = []
    for m in ub.matchup_set.filter(stage=sf_stage).order_by("position"):
        if m.winner_id:
            semi_losers.append(m.get_loser())
        else:
            semi_losers.append(None)
    while len(semi_losers) < 2:
        semi_losers.append(None)
    return [champion, runner_up, semi_losers[0], semi_losers[1]]


def serialize_top_four_picks(ub: UserBracket) -> list[dict[str, Any] | None]:
    return [_pick_payload(bc) for bc in top_four_bracket_contestants(ub)]
