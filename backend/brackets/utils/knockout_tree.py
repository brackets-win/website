"""
Create all Matchup rows for a single-elimination-only bracket (no group stage)
for a given UserBracket: first round is seeded, later rounds start empty and fill
via winner propagation.
"""
from __future__ import annotations

from typing import List

from django.db import transaction

from brackets.models import BracketContestant, BracketStage, Matchup, UserBracket


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
