"""Final-four picks from a user bracket for leaderboard display."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brackets.models import Bracket, BracketContestant, BracketStage, KnockoutStage, UserBracket
from brackets.utils.knockout_tree import _semifinal_stage_before_final
from brackets.utils.contestant_images import resolve_contestant_image_url


def _pick_payload(bc: BracketContestant | None) -> dict[str, Any] | None:
    if bc is None:
        return None
    name = bc.name_override or (
        bc.contestant.name if bc.contestant else f"Contestant {bc.id}"
    )
    c = bc.contestant
    img = resolve_contestant_image_url(c) if c else None
    return {
        "bracket_contestant_id": bc.id,
        "image_url": img,
        "display_name": name,
    }


@dataclass(frozen=True)
class TopFourContext:
    final_stage: BracketStage | None
    third_place_stage_id: int | None
    semifinal_stage: BracketStage | None
    has_third_place: bool


def build_top_four_context(bracket: Bracket) -> TopFourContext:
    final_ks = KnockoutStage.objects.filter(bracket=bracket, is_final=True).first()
    final_stage = BracketStage.objects.get(pk=final_ks.pk) if final_ks else None
    third_place_stage_id = None
    if bracket.has_third_place_match:
        third_ks = KnockoutStage.objects.filter(
            bracket=bracket, is_third_place=True
        ).first()
        if third_ks:
            third_place_stage_id = third_ks.pk
    semifinal_stage = (
        _semifinal_stage_before_final(bracket, final_stage)
        if final_stage is not None
        else None
    )
    return TopFourContext(
        final_stage=final_stage,
        third_place_stage_id=third_place_stage_id,
        semifinal_stage=semifinal_stage,
        has_third_place=bracket.has_third_place_match,
    )


def top_four_bracket_contestants(
    ub: UserBracket,
    ctx: TopFourContext | None = None,
) -> list[BracketContestant | None]:
    """
    Champion, runner-up, then either third-place winner & loser or two
    semifinal losers (left to right).
    """
    if ctx is None:
        ctx = build_top_four_context(ub.bracket)

    if ctx.final_stage is None:
        return [None, None, None, None]

    final_m = ub.matchup_set.filter(stage=ctx.final_stage).first()
    champion = final_m.winner if final_m else None
    runner_up = final_m.get_loser() if final_m and final_m.winner_id else None

    if ctx.has_third_place and ctx.third_place_stage_id is not None:
        tp_m = ub.matchup_set.filter(stage_id=ctx.third_place_stage_id).first()
        third_w = tp_m.winner if tp_m else None
        third_l = tp_m.get_loser() if tp_m and tp_m.winner_id else None
        return [champion, runner_up, third_w, third_l]

    if ctx.semifinal_stage is None:
        return [champion, runner_up, None, None]

    semi_losers: list[BracketContestant | None] = []
    for m in ub.matchup_set.filter(stage=ctx.semifinal_stage).order_by("position"):
        if m.winner_id:
            semi_losers.append(m.get_loser())
        else:
            semi_losers.append(None)
    while len(semi_losers) < 2:
        semi_losers.append(None)
    return [champion, runner_up, semi_losers[0], semi_losers[1]]


def serialize_top_four_picks(
    ub: UserBracket,
    ctx: TopFourContext | None = None,
) -> list[dict[str, Any] | None]:
    return [_pick_payload(bc) for bc in top_four_bracket_contestants(ub, ctx)]
