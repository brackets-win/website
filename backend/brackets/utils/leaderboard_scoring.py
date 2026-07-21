"""Materialized leaderboard scores — compute on write, read on GET."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db.models import Prefetch, Q

from brackets.models import (
    Bracket,
    BracketStage,
    GroupStage,
    KnockoutStage,
    Matchup,
    UserBracket,
)

logger = logging.getLogger(__name__)

LEADERBOARD_SCORES_KEY = "leaderboard_scores"
MASTER_SCORING_REVISION_KEY = "master_scoring_revision"
MASTER_SCORING_PENDING_KEY = "master_scoring_pending"
# Keep small: WC-sized brackets can take ~1s per entry to score.
MATERIALIZE_BATCH_SIZE = 10


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
    potential_rank: int | None
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


def is_master_scoring_pending(bracket: Bracket) -> bool:
    meta = bracket.metadata if isinstance(bracket.metadata, dict) else {}
    return bool(meta.get(MASTER_SCORING_PENDING_KEY))


def _clear_master_scoring_pending(bracket: Bracket) -> None:
    meta = dict(bracket.metadata) if isinstance(bracket.metadata, dict) else {}
    if not meta.pop(MASTER_SCORING_PENDING_KEY, None):
        return
    bracket.metadata = meta
    bracket.save(update_fields=["metadata"])


def mark_master_scoring_pending(bracket: Bracket) -> int:
    """Bump revision and flag scores stale without recomputing every entry."""
    revision = bump_master_scoring_revision(bracket)
    meta = dict(bracket.metadata) if isinstance(bracket.metadata, dict) else {}
    meta[MASTER_SCORING_PENDING_KEY] = True
    bracket.metadata = meta
    bracket.save(update_fields=["metadata"])
    return revision


def materialize_leaderboard_scores_for_bracket(bracket: Bracket) -> int:
    """Recompute all submitted user bracket scores for the current revision."""
    total = 0
    while True:
        result = materialize_leaderboard_scores_batch(bracket, limit=MATERIALIZE_BATCH_SIZE)
        total += result["updated_count"]
        if result["remaining_count"] == 0:
            return total


def _stale_submitted_user_brackets_qs(bracket: Bracket, revision: int):
    return UserBracket.objects.filter(
        bracket=bracket,
        is_master=False,
        submitted_at__isnull=False,
    ).filter(
        Q(leaderboard_scores_revision__isnull=True)
        | ~Q(leaderboard_scores_revision=revision)
    )


def count_stale_submitted_leaderboard_scores(bracket: Bracket) -> int:
    revision = get_master_scoring_revision(bracket)
    return _stale_submitted_user_brackets_qs(bracket, revision).count()


def materialize_leaderboard_scores_batch(
    bracket: Bracket,
    *,
    limit: int = MATERIALIZE_BATCH_SIZE,
) -> dict[str, int | bool]:
    """
    Recompute scores for up to ``limit`` submitted entries still on an old revision.

    Safe to call repeatedly from the client until ``remaining_count`` is zero.
    """
    bracket.refresh_from_db(fields=["metadata"])
    revision = get_master_scoring_revision(bracket)
    stale_qs = _stale_submitted_user_brackets_qs(bracket, revision).order_by("id")
    remaining_before = stale_qs.count()
    if remaining_before == 0:
        _clear_master_scoring_pending(bracket)
        # Scores already current, but ranks may be missing (e.g. brackets
        # confirmed before potential rank shipped). Backfill on demand.
        _backfill_potential_ranks_if_missing(bracket, revision)
        # Next-match selection doesn't change scores, so it can be pending on
        # its own. Recompute those picks here (the enumeration cost is what the
        # admin Apply pays for) without re-scoring every entry.
        _apply_pending_next_match_picks(bracket)
        return {
            "updated_count": 0,
            "remaining_count": 0,
            "leaderboard_scores_pending": False,
        }

    ctx = load_leaderboard_scoring_context(bracket)
    if not ctx.master:
        _clear_master_scoring_pending(bracket)
        return {
            "updated_count": 0,
            "remaining_count": 0,
            "leaderboard_scores_pending": False,
        }

    extras = _scoring_extras(ctx)
    updated_count = 0
    for ub in stale_qs.prefetch_related(_MATCHUP_PREFETCH)[:limit]:
        try:
            bundle = _compute_leaderboard_scores(
                ub,
                ctx,
                main_ko_stages=extras.main_ko_stages,
                groups_preview=extras.groups_preview,
                knockout_by_id=ctx.knockout_by_id,
            )
            _write_stored_scores(ub, revision, bundle)
            updated_count += 1
        except Exception:
            logger.exception(
                "Leaderboard materialize failed for user_bracket %s", ub.pk
            )

    if updated_count == 0 and remaining_before > 0:
        raise RuntimeError(
            "Could not update any leaderboard scores in this batch."
        )

    remaining_count = _stale_submitted_user_brackets_qs(
        bracket, get_master_scoring_revision(bracket)
    ).count()
    pending = remaining_count > 0 or is_master_scoring_pending(bracket)
    if remaining_count == 0:
        _clear_master_scoring_pending(bracket)
        pending = False
        from brackets.utils.next_match import clear_next_match_pending
        from brackets.utils.next_match_pick import (
            persist_next_match_picks_for_bracket,
        )
        from brackets.utils.potential_score import persist_all_potential_for_bracket

        try:
            persist_all_potential_for_bracket(bracket)
        except Exception:
            logger.exception(
                "Potential persist failed for bracket %s", bracket.pk
            )
        try:
            _warm_outcomes_cache_for_bracket(bracket)
        except Exception:
            logger.exception(
                "Outcomes cache warm failed for bracket %s", bracket.pk
            )
        try:
            persist_next_match_picks_for_bracket(bracket)
        except Exception:
            logger.exception(
                "Next match pick persist failed for bracket %s", bracket.pk
            )
        clear_next_match_pending(bracket)
    return {
        "updated_count": updated_count,
        "remaining_count": remaining_count,
        "leaderboard_scores_pending": pending,
    }


def _warm_outcomes_cache_for_bracket(bracket: Bracket) -> None:
    """Precompute outcomes for each challenge after master Apply."""
    from brackets.models import BracketChallenge
    from brackets.utils.challenge_outcomes import get_challenge_outcomes

    for challenge in BracketChallenge.objects.filter(bracket=bracket).only(
        "id", "metadata", "instance_type", "bracket_id"
    ):
        get_challenge_outcomes(challenge)


def _apply_pending_next_match_picks(bracket: Bracket) -> None:
    """Recompute next-match picks if flagged pending, then clear the flag."""
    from brackets.utils.next_match import (
        clear_next_match_pending,
        is_next_match_pending,
    )

    if not is_next_match_pending(bracket):
        return
    from brackets.utils.next_match_pick import persist_next_match_picks_for_bracket

    persist_next_match_picks_for_bracket(bracket)
    clear_next_match_pending(bracket)


def _backfill_potential_ranks_if_missing(bracket: Bracket, revision: int) -> None:
    """Compute ranks when entries are current but have no rank yet (e.g. older data)."""
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket
    from brackets.utils.potential_rank import (
        persist_potential_ranks_for_bracket,
        potential_rank_allowed_for_bracket,
    )

    if omit_leaderboard_potential_for_bracket(bracket):
        return
    if not potential_rank_allowed_for_bracket(bracket):
        return
    missing = UserBracket.objects.filter(
        bracket=bracket,
        is_master=False,
        submitted_at__isnull=False,
        leaderboard_scores_revision=revision,
        leaderboard_potential_rank__isnull=True,
    ).exists()
    if not missing:
        return
    from brackets.utils.potential_rank import persist_potential_ranks_for_bracket

    try:
        persist_potential_ranks_for_bracket(bracket)
    except Exception:
        logger.exception(
            "Potential rank backfill failed for bracket %s", bracket.pk
        )


def on_master_bracket_changed(bracket: Bracket, *, materialize: bool = True) -> int:
    """Invalidate master revision; optionally recompute all submitted brackets."""
    if materialize:
        bump_master_scoring_revision(bracket)
        count = refresh_all_submitted_leaderboard_scores_for_bracket(bracket)
        _clear_master_scoring_pending(bracket)
        return count
    return mark_master_scoring_pending(bracket)


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
        potential_rank=None,
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
        potential_rank=ub.leaderboard_potential_rank,
        stage_scores=stage_scores,
    )


def read_stored_leaderboard_scores(
    ub: UserBracket,
    *,
    revision: int | None = None,
) -> LeaderboardScoreBundle:
    """Read materialized scores only — never computes on the request path."""
    if ub.is_master or ub.submitted_at is None:
        return LeaderboardScoreBundle(
            score=None, potential=None, potential_rank=None, stage_scores={}
        )

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

    return LeaderboardScoreBundle(
        score=None, potential=None, potential_rank=None, stage_scores={}
    )


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
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket

    omit_potential = omit_leaderboard_potential_for_bracket(ub.bracket)
    ub.leaderboard_score = bundle.score
    if not omit_potential and bundle.potential is not None:
        ub.leaderboard_potential = bundle.potential
    ub.leaderboard_stage_scores = bundle.stage_scores
    ub.leaderboard_scores_revision = revision

    meta = dict(ub.metadata) if isinstance(ub.metadata, dict) else {}
    cache: dict[str, object] = {
        "revision": revision,
        "score": bundle.score,
        "stage_scores": bundle.stage_scores,
    }
    if not omit_potential and bundle.potential is not None:
        cache["potential"] = bundle.potential
    meta[LEADERBOARD_SCORES_KEY] = cache
    ub.metadata = meta
    update_fields = [
        "leaderboard_score",
        "leaderboard_stage_scores",
        "leaderboard_scores_revision",
        "metadata",
    ]
    if not omit_potential and bundle.potential is not None:
        update_fields.insert(1, "leaderboard_potential")
    ub.save(update_fields=update_fields)


def _compute_leaderboard_scores(
    ub: UserBracket,
    ctx: LeaderboardScoringContext,
    *,
    main_ko_stages=None,
    groups_preview=None,
    knockout_by_id=None,
) -> LeaderboardScoreBundle:
    if not ctx.master:
        return LeaderboardScoreBundle(
            score=None, potential=None, potential_rank=None, stage_scores={}
        )

    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket

    del main_ko_stages, groups_preview, knockout_by_id, omit_leaderboard_potential_for_bracket

    stage_scores = stage_scores_for_user_bracket(ub, ctx)
    score = sum(v for v in stage_scores.values() if v is not None)
    return LeaderboardScoreBundle(
        score=score,
        potential=None,
        potential_rank=None,
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
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket

    if not omit_leaderboard_potential_for_bracket(ub.bracket):
        potential = ub.calculate_potential_score(
            master=ctx.master,
            groups_preview=extras.groups_preview,
        )
        bundle = LeaderboardScoreBundle(
            score=bundle.score,
            potential=potential,
            potential_rank=bundle.potential_rank,
            stage_scores=bundle.stage_scores,
        )
    _write_stored_scores(ub, revision, bundle)
    from brackets.utils.next_match_pick import persist_next_match_pick_for_user_bracket

    persist_next_match_pick_for_user_bracket(ub)


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
    from brackets.utils.next_match import clear_next_match_pending
    from brackets.utils.next_match_pick import persist_next_match_picks_for_bracket
    from brackets.utils.potential_score import persist_all_potential_for_bracket

    persist_all_potential_for_bracket(bracket)
    persist_next_match_picks_for_bracket(bracket)
    clear_next_match_pending(bracket)
    return len(ubs)


@dataclass(frozen=True)
class LeaderboardStageColumnPlan:
    """Which stage columns to show and which scores to fold into others."""

    hidden_stage_ids: frozenset[int]
    # source stage id -> destination stage id (fold source points into dest)
    merge_into: dict[int, int]


def leaderboard_stage_column_plan(
    ctx: LeaderboardScoringContext,
) -> LeaderboardStageColumnPlan:
    """Decide hidden / merged stage columns for the prediction leaderboard.

    - Knockout-only: hide the seeded first KO column (no picks, always full).
    - Group → knockout: when the first KO has ``combine_points_with_group_stage``,
      hide that KO column and fold its points into the preceding group column.
    """
    stages = list(ctx.stages)
    has_group_stage = any(
        s.stage_type == BracketStage.StageType.GROUP for s in stages
    )
    first_ko = next(
        (s for s in stages if s.stage_type == BracketStage.StageType.KNOCKOUT),
        None,
    )
    hidden: set[int] = set()
    merge_into: dict[int, int] = {}

    if first_ko is None:
        return LeaderboardStageColumnPlan(
            hidden_stage_ids=frozenset(),
            merge_into={},
        )

    if not has_group_stage:
        hidden.add(first_ko.id)
        return LeaderboardStageColumnPlan(
            hidden_stage_ids=frozenset(hidden),
            merge_into={},
        )

    ks = ctx.knockout_by_id.get(first_ko.pk)
    if ks is not None and ks.combine_points_with_group_stage:
        group_stage = next(
            (
                s
                for s in stages
                if s.stage_type == BracketStage.StageType.GROUP
                and s.order < first_ko.order
            ),
            None,
        )
        if group_stage is not None:
            hidden.add(first_ko.id)
            merge_into[first_ko.id] = group_stage.id

    return LeaderboardStageColumnPlan(
        hidden_stage_ids=frozenset(hidden),
        merge_into=merge_into,
    )


def fold_merged_stage_scores(
    stage_scores: dict[str, int | None],
    merge_into: dict[int, int],
) -> dict[str, int | None]:
    """Return a copy of ``stage_scores`` with merged stage keys folded in."""
    if not merge_into:
        return stage_scores
    out = dict(stage_scores)
    for source_id, dest_id in merge_into.items():
        source_key = f"stage:{source_id}"
        dest_key = f"stage:{dest_id}"
        source_val = out.pop(source_key, None)
        dest_val = out.get(dest_key)
        if source_val is None and dest_val is None:
            out[dest_key] = None
        elif source_val is None:
            out[dest_key] = dest_val
        elif dest_val is None:
            out[dest_key] = source_val
        else:
            out[dest_key] = dest_val + source_val
    return out


def compute_leaderboard_denominators(
    ctx: LeaderboardScoringContext,
    *,
    hidden_stage_id: int | None = None,
    hidden_stage_ids: frozenset[int] | set[int] | None = None,
    merge_into: dict[int, int] | None = None,
) -> dict[str, object]:
    """Per-column denominators for the leaderboard PTS/% toggle.

    Stage, champion, and total denominators use the master's *currently
    available* points (what a perfect entry could have earned so far). These
    drive the dash-before-results rule and the % conversion for those columns.

    The potential denominator is the score of the *fully completed* perfect
    bracket — a structural constant from the scoring rules, independent of
    current results — matching the structural upper bound used for potential
    points (group achievables plus full knockout tree).

    When ``hidden_stage_ids`` / ``merge_into`` are omitted, uses
    ``leaderboard_stage_column_plan`` (combine first KO into group when set;
    hide seeded first KO on knockout-only brackets). Pass an empty frozenset
    / dict to disable that plan (legacy callers that already pass
    ``hidden_stage_id`` keep working).
    """
    columns: dict[str, int] = {}
    result: dict[str, object] = {"total": 0, "potential": 0, "columns": columns}

    master = ctx.master
    if master is None:
        return result

    from brackets.utils.group_stage_config import group_stage_pick_requirements
    from brackets.utils.sync_group_knockout import (
        contestants_credited_for_knockout_score,
    )

    if hidden_stage_ids is None and merge_into is None and hidden_stage_id is None:
        plan = leaderboard_stage_column_plan(ctx)
        hidden = set(plan.hidden_stage_ids)
        merges = dict(plan.merge_into)
    else:
        hidden = set(hidden_stage_ids or ())
        if hidden_stage_id is not None:
            hidden.add(hidden_stage_id)
        merges = dict(merge_into or {})

    bracket = master.bracket
    current_total = 0
    perfect_total = 0

    for stage in ctx.stages:
        key = f"stage:{stage.id}"
        if stage.stage_type == BracketStage.StageType.GROUP:
            gs = ctx.group_by_id.get(stage.pk)
            if gs is None:
                continue
            current = master._calculate_group_stage_score(
                master, stage, group_stage=gs
            )
            _, third_count = group_stage_pick_requirements(gs)
            from brackets.utils.group_stage_config import group_stage_scorable_ranks

            scorable = group_stage_scorable_ranks(gs)
            perfect = gs.points_per_exact_position * scorable * gs.number_of_groups + (
                gs.points_per_advancer
                * (
                    gs.contestants_qualifying_per_group * gs.number_of_groups
                    + third_count
                )
            )
        elif stage.stage_type == BracketStage.StageType.KNOCKOUT:
            ks = ctx.knockout_by_id.get(stage.pk)
            if ks is None:
                continue
            if ks.is_third_place:
                current = master._calculate_third_place_stage_score(master, stage)
                perfect = bracket.points_third_place_winner
            else:
                pts = ks.points_per_correct_pick
                current = (
                    len(contestants_credited_for_knockout_score(master, stage))
                    * pts
                )
                perfect = ks.number_of_contestants * pts
        else:
            continue

        # Perfect-complete total spans every scored stage (including a seeded
        # first round) to match the potential numerator's stage set.
        perfect_total += perfect
        if stage.id in hidden:
            dest_id = merges.get(stage.id)
            if dest_id is not None:
                dest_key = f"stage:{dest_id}"
                columns[dest_key] = columns.get(dest_key, 0) + current
                current_total += current
            continue
        columns[key] = columns.get(key, 0) + current
        current_total += current

    champion_current = (
        bracket.points_champion if master.get_final_matchup_winner() else 0
    )
    columns["champion"] = champion_current
    current_total += champion_current
    perfect_total += bracket.points_champion

    result["total"] = current_total
    result["potential"] = perfect_total
    return result


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
