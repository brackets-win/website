"""Bracket-level third-place game (auto stage + matchup wiring)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from brackets.models import (
    Bracket,
    BracketStage,
    KnockoutStage,
    Matchup,
    UserBracket,
)
from brackets.utils.bracket_structure_config import resolved_knockout_defaults
from brackets.utils.knockout_tree import (
    _semifinal_stage_before_final,
    ensure_third_place_matchup_wired,
)


def get_third_place_stage(bracket: Bracket) -> KnockoutStage | None:
    return KnockoutStage.objects.filter(
        bracket=bracket, is_third_place=True
    ).first()


@transaction.atomic
def sync_third_place_structure(bracket: Bracket) -> None:
    """
    Keep third-place storage in sync with ``bracket.has_third_place_match``.

  When enabled: ensure one internal knockout stage and wired matchups on every
    user bracket. When disabled: remove that stage (matchups cascade).
    """
    if bracket.has_third_place_match:
        stage = _ensure_third_place_stage(bracket)
        _ensure_matchups_for_all_user_brackets(bracket, stage)
    else:
        _remove_third_place_stage(bracket)


def _ensure_third_place_stage(bracket: Bracket) -> KnockoutStage:
    existing = get_third_place_stage(bracket)
    if existing:
        return existing

    final = KnockoutStage.objects.filter(bracket=bracket, is_final=True).first()
    if final:
        order = final.order + 1
    else:
        max_order = (
            bracket.stages.aggregate(m=Max("order"))["m"] or 0
        )
        order = max_order + 1

    ko_defaults = resolved_knockout_defaults(bracket.metadata)
    return KnockoutStage.objects.create(
        bracket=bracket,
        name="Third place",
        order=order,
        stage_type=BracketStage.StageType.KNOCKOUT,
        number_of_contestants=2,
        contestants_advancing=1,
        is_final=False,
        is_third_place=True,
        **ko_defaults,
    )


def _remove_third_place_stage(bracket: Bracket) -> None:
    KnockoutStage.objects.filter(bracket=bracket, is_third_place=True).delete()


def _semifinal_matchups_ready(user_bracket: UserBracket, bracket: Bracket) -> bool:
    """True when both semifinal slots exist (wiring can run safely)."""
    final = KnockoutStage.objects.filter(bracket=bracket, is_final=True).first()
    if not final:
        return False
    final_stage = BracketStage.objects.get(pk=final.pk)
    sf_stage = _semifinal_stage_before_final(bracket, final_stage)
    if not sf_stage:
        return False
    return (
        Matchup.objects.filter(user_bracket=user_bracket, stage=sf_stage).count() == 2
    )


def _ensure_matchups_for_all_user_brackets(
    bracket: Bracket, stage: KnockoutStage
) -> None:
    for ub in UserBracket.objects.filter(bracket=bracket):
        if not _semifinal_matchups_ready(ub, bracket):
            continue
        ensure_third_place_matchup_wired(ub, stage, bracket=bracket)
