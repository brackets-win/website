"""
Create all Matchup rows for a single-elimination-only bracket (no group stage)
for a given UserBracket: first round is seeded, later rounds start empty and fill
via winner propagation.
"""
from __future__ import annotations

from typing import List

from django.db import transaction

from brackets.models import (
    BracketContestant,
    BracketStage,
    KnockoutStage,
    Matchup,
    UserBracket,
)


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
            final_ks = KnockoutStage.objects.filter(
                bracket=bracket, is_final=True
            ).first()
            if not final_ks:
                raise ValueError('Third place stage requires a final stage on bracket.')
            final_stage = BracketStage.objects.get(pk=final_ks.pk)
            sf_stage = (
                bracket.stages.filter(
                    stage_type=BracketStage.StageType.KNOCKOUT,
                    order__lt=final_stage.order,
                )
                .order_by('-order')
                .first()
            )
            if not sf_stage:
                raise ValueError(
                    'Third place requires a knockout stage before the final.'
                )
            sf_pair = list(
                Matchup.objects.filter(
                    user_bracket=user_bracket, stage=sf_stage
                ).order_by('position')
            )
            if len(sf_pair) != 2:
                raise ValueError('Expected two semifinal matchups for third-place wiring.')
            m = Matchup.objects.create(
                user_bracket=user_bracket,
                stage=stage,
                position=1,
                source_a_matchup=sf_pair[0],
                source_a_uses_winner=False,
                source_b_matchup=sf_pair[1],
                source_b_uses_winner=False,
            )
            created.append(m)
            continue

        if idx == 0:
            for position in range(1, num_matchups + 1):
                c1 = contestants[position - 1]
                c2 = contestants[n - position]
                created.append(
                    Matchup.objects.create(
                        user_bracket=user_bracket,
                        stage=stage,
                        position=position,
                        contestant1=c1,
                        contestant2=c2,
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
        return ensure_full_knockout_matchups(user_bracket)
    if _bracket_has_group_stage(bracket):
        return ensure_knockout_matchup_shell(user_bracket)
    raise ValueError("Bracket has no knockout stages.")
