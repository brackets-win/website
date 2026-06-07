"""
Create all Matchup rows for a single-elimination-only bracket (no group stage)
for a given UserBracket: first round is seeded, later rounds start empty and fill
via winner propagation.
"""
from __future__ import annotations

from typing import List

from django.db import transaction

from brackets.models import (
    Bracket,
    BracketContestant,
    BracketStage,
    KnockoutStage,
    Matchup,
    UserBracket,
)
def _semifinal_stage_before_final(bracket, final_stage: BracketStage) -> BracketStage | None:
    """Knockout stage immediately before the final (feeds semi winners/losers)."""
    return (
        bracket.stages.filter(
            stage_type=BracketStage.StageType.KNOCKOUT,
            order=final_stage.order - 1,
        )
        .first()
    )


def ensure_third_place_matchup_wired(
    user_bracket: UserBracket,
    third_place_stage: BracketStage,
    *,
    bracket: Bracket | None = None,
) -> Matchup:
    """
    One third-place game: losers of the two semifinal matchups (``uses_winner=False``).
    """
    bracket = bracket or user_bracket.bracket
    final_ks = KnockoutStage.objects.filter(bracket=bracket, is_final=True).first()
    if not final_ks:
        raise ValueError("Third place stage requires a final stage on bracket.")

    final_stage = BracketStage.objects.get(pk=final_ks.pk)
    sf_stage = _semifinal_stage_before_final(bracket, final_stage)
    if not sf_stage:
        raise ValueError("Third place requires a knockout stage before the final.")

    sf_pair = list(
        Matchup.objects.filter(
            user_bracket=user_bracket,
            stage=sf_stage,
        ).order_by("position")
    )
    if len(sf_pair) != 2:
        raise ValueError("Expected two semifinal matchups for third-place wiring.")

    m, created = Matchup.objects.get_or_create(
        user_bracket=user_bracket,
        stage=third_place_stage,
        position=1,
        defaults={
            "source_a_matchup": sf_pair[0],
            "source_a_uses_winner": False,
            "source_b_matchup": sf_pair[1],
            "source_b_uses_winner": False,
        },
    )
    if not created:
        changed = False
        if m.source_a_matchup_id != sf_pair[0].pk:
            m.source_a_matchup = sf_pair[0]
            m.source_a_uses_winner = False
            changed = True
        if m.source_b_matchup_id != sf_pair[1].pk:
            m.source_b_matchup = sf_pair[1]
            m.source_b_uses_winner = False
            changed = True
        if changed:
            m.save(
                update_fields=[
                    "source_a_matchup",
                    "source_a_uses_winner",
                    "source_b_matchup",
                    "source_b_uses_winner",
                ]
            )
    return m


def _is_single_elim_knockout_only(bracket) -> bool:
    return (
        not bracket.stages.filter(stage_type=BracketStage.StageType.GROUP).exists()
        and bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT).exists()
    )


@transaction.atomic
def ensure_full_knockout_matchups(user_bracket: UserBracket) -> List[Matchup]:
    """
    Idempotently ensure Matchup rows exist for every knockout stage.

    Raises ValueError if the bracket has a group stage (different mapping rules).
    """
    bracket = user_bracket.bracket
    if not _is_single_elim_knockout_only(bracket):
        raise ValueError(
            'Bracket has a group stage or no knockout stages — seed matchups manually.'
        )

    ko_stages = list(
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT).order_by(
            'order'
        )
    )
    if not ko_stages:
        raise ValueError('No knockout stages on bracket.')

    contestants = list(
        BracketContestant.objects.filter(bracket=bracket).order_by('seed', 'id')
    )
    if len(contestants) != ko_stages[0].number_of_contestants:
        raise ValueError(
            f'Contestant count ({len(contestants)}) must match first knockout stage '
            f'({ko_stages[0].number_of_contestants}).'
        )

    n = len(contestants)
    created: List[Matchup] = []

    for idx, stage in enumerate(ko_stages):
        num_matchups = stage.number_of_contestants // 2
        existing = Matchup.objects.filter(user_bracket=user_bracket, stage=stage)
        if existing.exists():
            continue

        ks = KnockoutStage.objects.filter(pk=stage.pk).first()
        if ks and ks.is_third_place:
            created.append(
                ensure_third_place_matchup_wired(
                    user_bracket, stage, bracket=bracket
                )
            )
            continue

        if idx == 0:
            from brackets.utils.bracket_seeding import first_round_seed_pairs

            for position, (seed1, seed2) in enumerate(
                first_round_seed_pairs(n), start=1
            ):
                created.append(
                    Matchup.objects.create(
                        user_bracket=user_bracket,
                        stage=stage,
                        position=position,
                        contestant1=contestants[seed1 - 1],
                        contestant2=contestants[seed2 - 1],
                    )
                )
        else:
            for position in range(1, num_matchups + 1):
                created.append(
                    Matchup.objects.create(
                        user_bracket=user_bracket,
                        stage=stage,
                        position=position,
                    )
                )

    return created


def _bracket_has_group_stage(bracket) -> bool:
    return bracket.stages.filter(
        stage_type=BracketStage.StageType.GROUP
    ).exists()


@transaction.atomic
def clear_knockout_source_wiring(
    user_bracket: UserBracket,
    *,
    keep_third_place: bool = True,
) -> int:
    """
    Remove explicit ``source_*_matchup`` links so winners advance by tree position
    (1–2 → next round slot 1, 3–4 → slot 2, …). Third-place game wiring is kept.
    """
    cleared = 0
    for stage in user_bracket.bracket.stages.filter(
        stage_type=BracketStage.StageType.KNOCKOUT
    ):
        ks = KnockoutStage.objects.filter(pk=stage.pk).first()
        if keep_third_place and ks and ks.is_third_place:
            continue
        n = (
            Matchup.objects.filter(user_bracket=user_bracket, stage=stage)
            .exclude(source_a_matchup__isnull=True, source_b_matchup__isnull=True)
            .update(
                source_a_matchup=None,
                source_b_matchup=None,
                source_a_uses_winner=True,
                source_b_uses_winner=True,
            )
        )
        cleared += n
    return cleared


@transaction.atomic
def ensure_knockout_matchup_shell(user_bracket: UserBracket) -> List[Matchup]:
    """
    Idempotently create empty matchup rows for every knockout stage (group → knockout
    brackets). First-round slots stay empty until fed from group results / picks.
    """
    bracket = user_bracket.bracket
    ko_stages = list(
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT).order_by(
            "order"
        )
    )
    if not ko_stages:
        return []

    created: List[Matchup] = []
    for stage in ko_stages:
        ks = KnockoutStage.objects.filter(pk=stage.pk).first()
        if ks and ks.is_third_place:
            m, was_created = Matchup.objects.get_or_create(
                user_bracket=user_bracket,
                stage=stage,
                position=1,
                defaults={},
            )
            ensure_third_place_matchup_wired(user_bracket, stage, bracket=bracket)
            if was_created:
                created.append(m)
            continue

        num_matchups = stage.number_of_contestants // 2
        for position in range(1, num_matchups + 1):
            m, was_created = Matchup.objects.get_or_create(
                user_bracket=user_bracket,
                stage=stage,
                position=position,
                defaults={},
            )
            if was_created:
                created.append(m)

    return created


def ensure_knockout_structure_for_user_bracket(user_bracket: UserBracket) -> List[Matchup]:
    """
    Single-elimination without groups: seeded first round.
    With a group stage: empty knockout shell only.
    """
    bracket = user_bracket.bracket
    if _is_single_elim_knockout_only(bracket):
        first_ko = (
            bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT)
            .order_by("order")
            .first()
        )
        if first_ko is None:
            raise ValueError("Bracket has no knockout stages.")
        contestant_count = BracketContestant.objects.filter(bracket=bracket).count()
        # Allow tournament-style setup before contestants are assigned:
        # create the knockout shell so the bracket UI is immediately visible.
        if contestant_count != first_ko.number_of_contestants:
            return ensure_knockout_matchup_shell(user_bracket)
        return ensure_full_knockout_matchups(user_bracket)
    if _bracket_has_group_stage(bracket):
        return ensure_knockout_matchup_shell(user_bracket)
    raise ValueError("Bracket has no knockout stages.")
