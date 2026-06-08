"""Shared scoring context for leaderboard endpoints and home-page previews."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Prefetch

from brackets.models import (
    Bracket,
    BracketStage,
    GroupStage,
    KnockoutStage,
    Matchup,
    UserBracket,
)


@dataclass
class LeaderboardScoringContext:
    master: UserBracket | None
    stages: tuple[BracketStage, ...]
    knockout_by_id: dict[int, KnockoutStage]
    group_by_id: dict[int, GroupStage]


_MATCHUP_PREFETCH = Prefetch(
    "matchup_set",
    queryset=Matchup.objects.select_related(
        "winner__contestant",
        "contestant1__contestant",
        "contestant2__contestant",
        "stage",
    ),
)


def load_leaderboard_scoring_context(bracket: Bracket) -> LeaderboardScoringContext:
    master = bracket.userbracket_set.filter(is_master=True).first()
    if master is not None:
        master = (
            UserBracket.objects.filter(pk=master.pk)
            .prefetch_related(_MATCHUP_PREFETCH)
            .first()
        )
    stages = tuple(bracket.stages.order_by("order"))
    knockout_by_id = {
        ks.pk: ks for ks in KnockoutStage.objects.filter(bracket=bracket)
    }
    group_by_id = {
        gs.pk: gs for gs in GroupStage.objects.filter(bracket=bracket)
    }
    return LeaderboardScoringContext(
        master=master,
        stages=stages,
        knockout_by_id=knockout_by_id,
        group_by_id=group_by_id,
    )


def total_score_for_user_bracket(
    ub: UserBracket,
    ctx: LeaderboardScoringContext,
) -> int | None:
    if not ctx.master:
        return None
    total = 0
    for stage in ctx.stages:
        stage_score = ub.calculate_stage_score(
            stage,
            master=ctx.master,
            knockout_stage=ctx.knockout_by_id.get(stage.pk),
            group_stage=ctx.group_by_id.get(stage.pk),
        )
        if stage_score is not None:
            total += stage_score
    champion = ub.calculate_champion_score(master=ctx.master)
    if champion is not None:
        total += champion
    return total


def stage_scores_for_user_bracket(
    ub: UserBracket,
    ctx: LeaderboardScoringContext,
) -> dict[str, int | None]:
    stage_scores: dict[str, int | None] = {
        f"stage:{stage.id}": ub.calculate_stage_score(
            stage,
            master=ctx.master,
            knockout_stage=ctx.knockout_by_id.get(stage.pk),
            group_stage=ctx.group_by_id.get(stage.pk),
        )
        for stage in ctx.stages
    }
    stage_scores["champion"] = ub.calculate_champion_score(master=ctx.master)
    return stage_scores
