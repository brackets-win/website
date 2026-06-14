"""Materialized leaderboard scores — compute on write, read on GET."""

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

LEADERBOARD_SCORES_KEY = "leaderboard_scores"
MASTER_SCORING_REVISION_KEY = "master_scoring_revision"


@dataclass
class LeaderboardScoringContext:
    master: UserBracket | None
    stages: tuple[BracketStage, ...]
    knockout_by_id: dict[int, KnockoutStage]
    group_by_id: dict[int, GroupStage]


@dataclass
class LeaderboardScoreBundle:
    score: int | None
    potential: int | None
    stage_scores: dict[str, int | None]


@dataclass(frozen=True)
class _ScoringExtras:
    main_ko_stages: list[BracketStage]
    groups_preview: list


_MATCHUP_PREFETCH = Prefetch(
    "matchup_set",
    queryset=Matchup.objects.select_related(
        "winner__contestant",
        "contestant1__contestant",
        "contestant2__contestant",
        "stage",
    ),
)


def get_master_scoring_revision(bracket: Bracket) -> int:
    meta = bracket.metadata if isinstance(bracket.metadata, dict) else {}
    return int(meta.get(MASTER_SCORING_REVISION_KEY) or 0)


def bump_master_scoring_revision(bracket: Bracket) -> int:
    meta = dict(bracket.metadata) if isinstance(bracket.metadata, dict) else {}
    revision = int(meta.get(MASTER_SCORING_REVISION_KEY) or 0) + 1
    meta[MASTER_SCORING_REVISION_KEY] = revision
    bracket.metadata = meta
    bracket.save(update_fields=["metadata"])
    return revision


def on_master_bracket_changed(bracket: Bracket) -> int:
    """Invalidate master revision and recompute all submitted user brackets."""
    bump_master_scoring_revision(bracket)
    return refresh_all_submitted_leaderboard_scores_for_bracket(bracket)


def _read_metadata_scores(
    ub: UserBracket, revision: int
) -> LeaderboardScoreBundle | None:
    meta = ub.metadata if isinstance(ub.metadata, dict) else {}
    cache = meta.get(LEADERBOARD_SCORES_KEY)
    if not isinstance(cache, dict):
        return None
    if cache.get("revision") != revision:
        return None
    stage_scores = cache.get("stage_scores")
    if not isinstance(stage_scores, dict):
        return None
    return LeaderboardScoreBundle(
        score=cache.get("score"),
        potential=cache.get("potential"),
        stage_scores=stage_scores,
    )


def _bundle_from_stored_fields(ub: UserBracket) -> LeaderboardScoreBundle | None:
    if ub.leaderboard_score is None:
        return None
    stage_scores = ub.leaderboard_stage_scores
    if not isinstance(stage_scores, dict):
        stage_scores = {}
    return LeaderboardScoreBundle(
        score=ub.leaderboard_score,
        potential=ub.leaderboard_potential,
        stage_scores=stage_scores,
    )


def read_stored_leaderboard_scores(
    ub: UserBracket,
    *,
    revision: int | None = None,
) -> LeaderboardScoreBundle:
    """Read materialized scores only — never computes on the request path."""
    if ub.is_master or ub.submitted_at is None:
        return LeaderboardScoreBundle(score=None, potential=None, stage_scores={})

    rev = revision if revision is not None else get_master_scoring_revision(ub.bracket)

    if ub.leaderboard_scores_revision == rev:
        current = _bundle_from_stored_fields(ub)
        if current is not None:
            return current

    legacy = _read_metadata_scores(ub, rev)
    if legacy is not None:
        return legacy

    stale = _bundle_from_stored_fields(ub)
    if stale is not None:
        return stale

    return LeaderboardScoreBundle(score=None, potential=None, stage_scores={})


def get_leaderboard_scores(
    ub: UserBracket,
    ctx: LeaderboardScoringContext | None = None,
    *,
    revision: int | None = None,
    main_ko_stages=None,
    groups_preview=None,
    knockout_by_id=None,
    write_cache: bool = True,
) -> LeaderboardScoreBundle:
    """Backward-compatible alias for read_stored_leaderboard_scores."""
    del ctx, main_ko_stages, groups_preview, knockout_by_id, write_cache
    return read_stored_leaderboard_scores(ub, revision=revision)


def _write_stored_scores(
    ub: UserBracket,
    revision: int,
    bundle: LeaderboardScoreBundle,
) -> None:
    ub.leaderboard_score = bundle.score
    ub.leaderboard_potential = bundle.potential
    ub.leaderboard_stage_scores = bundle.stage_scores
    ub.leaderboard_scores_revision = revision

    meta = dict(ub.metadata) if isinstance(ub.metadata, dict) else {}
    meta[LEADERBOARD_SCORES_KEY] = {
        "revision": revision,
        "score": bundle.score,
        "potential": bundle.potential,
        "stage_scores": bundle.stage_scores,
    }
    ub.metadata = meta
    ub.save(
        update_fields=[
            "leaderboard_score",
            "leaderboard_potential",
            "leaderboard_stage_scores",
            "leaderboard_scores_revision",
            "metadata",
        ]
    )


def _compute_leaderboard_scores(
    ub: UserBracket,
    ctx: LeaderboardScoringContext,
    *,
    main_ko_stages=None,
    groups_preview=None,
    knockout_by_id=None,
) -> LeaderboardScoreBundle:
    if not ctx.master:
        return LeaderboardScoreBundle(score=None, potential=None, stage_scores={})

    stage_scores = stage_scores_for_user_bracket(ub, ctx)
    score = sum(v for v in stage_scores.values() if v is not None)
    potential = ub.calculate_potential_score(
        master=ctx.master,
        main_ko_stages=main_ko_stages,
        groups_preview=groups_preview,
        knockout_by_id=knockout_by_id or ctx.knockout_by_id,
    )
    return LeaderboardScoreBundle(
        score=score,
        potential=potential,
        stage_scores=stage_scores,
    )


def _scoring_extras(ctx: LeaderboardScoringContext) -> _ScoringExtras:
    from brackets.api.serializers import bracket_groups_preview

    third_place_ids = {
        ks.pk for ks in ctx.knockout_by_id.values() if ks.is_third_place
    }
    main_ko_stages = [
        s
        for s in ctx.stages
        if s.stage_type == BracketStage.StageType.KNOCKOUT
        and s.pk not in third_place_ids
    ]
    return _ScoringExtras(
        main_ko_stages=main_ko_stages,
        groups_preview=bracket_groups_preview(ctx.master.bracket),
    )


def refresh_user_bracket_leaderboard_cache(ub: UserBracket) -> None:
    if ub.is_master or ub.submitted_at is None:
        return
    ctx = load_leaderboard_scoring_context(ub.bracket)
    if not ctx.master:
        return
    extras = _scoring_extras(ctx)
    revision = get_master_scoring_revision(ub.bracket)
    bundle = _compute_leaderboard_scores(
        ub,
        ctx,
        main_ko_stages=extras.main_ko_stages,
        groups_preview=extras.groups_preview,
        knockout_by_id=ctx.knockout_by_id,
    )
    _write_stored_scores(ub, revision, bundle)


def refresh_all_submitted_leaderboard_scores_for_bracket(bracket: Bracket) -> int:
    ctx = load_leaderboard_scoring_context(bracket)
    if not ctx.master:
        return 0

    extras = _scoring_extras(ctx)
    revision = get_master_scoring_revision(bracket)
    ubs = list(
        UserBracket.objects.filter(
            bracket=bracket,
            is_master=False,
            submitted_at__isnull=False,
        ).prefetch_related(_MATCHUP_PREFETCH)
    )
    for ub in ubs:
        bundle = _compute_leaderboard_scores(
            ub,
            ctx,
            main_ko_stages=extras.main_ko_stages,
            groups_preview=extras.groups_preview,
            knockout_by_id=ctx.knockout_by_id,
        )
        _write_stored_scores(ub, revision, bundle)
    return len(ubs)


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
    ctx: LeaderboardScoringContext | None = None,
    *,
    revision: int | None = None,
) -> int | None:
    del ctx
    return read_stored_leaderboard_scores(ub, revision=revision).score


def score_for_leaderboard_preview(
    ub: UserBracket,
    ctx: LeaderboardScoringContext | None = None,
    *,
    revision: int | None = None,
) -> int | None:
    del ctx
    return read_stored_leaderboard_scores(ub, revision=revision).score


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
