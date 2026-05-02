"""Serialize domain models to JSON-friendly dicts for API responses."""

from __future__ import annotations

from typing import Any

from brackets.models import (
    Bracket,
    BracketContestant,
    BracketStage,
    GroupStage,
    KnockoutStage,
    Matchup,
    UserBracket,
)


def contestant_public(bc: BracketContestant) -> dict[str, Any]:
    name = bc.name_override or (
        bc.contestant.name if bc.contestant else f"Contestant {bc.id}"
    )
    return {
        "id": bc.id,
        "display_name": name,
        "seed": bc.seed,
        "contestant_id": bc.contestant_id,
        "image_url": bc.contestant.image_url if bc.contestant else None,
    }


def stage_public(stage: BracketStage) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": stage.id,
        "name": stage.name,
        "order": stage.order,
        "stage_type": stage.stage_type,
        "number_of_contestants": stage.number_of_contestants,
        "submission_deadline": (
            stage.submission_deadline.isoformat()
            if stage.submission_deadline
            else None
        ),
        "points_per_correct_pick": stage.points_per_correct_pick,
        "metadata": stage.metadata,
    }
    if stage.stage_type == BracketStage.StageType.KNOCKOUT:
        ks = KnockoutStage.objects.get(pk=stage.pk)
        base["knockout"] = {
            "is_final": ks.is_final,
            "number_of_legs": ks.number_of_legs,
        }
    elif stage.stage_type == BracketStage.StageType.GROUP:
        gs = GroupStage.objects.get(pk=stage.pk)
        base["group"] = {
            "number_of_groups": gs.number_of_groups,
            "matches_per_contestant": gs.matches_per_contestant,
        }
    return base


def matchup_public(m: Matchup) -> dict[str, Any]:
    return {
        "id": m.id,
        "stage_id": m.stage_id,
        "position": m.position,
        "contestant1": contestant_public(m.contestant1) if m.contestant1 else None,
        "contestant2": contestant_public(m.contestant2) if m.contestant2 else None,
        "winner": contestant_public(m.winner) if m.winner else None,
        "source_a_matchup_id": m.source_a_matchup_id,
        "source_b_matchup_id": m.source_b_matchup_id,
    }


def bracket_summary(b: Bracket) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "description": b.description,
        "created_at": b.created_at.isoformat(),
        "randomize_seeds_per_challenge": b.randomize_seeds_per_challenge,
        "metadata": b.metadata,
    }


def bracket_detail(b: Bracket) -> dict[str, Any]:
    stages = [stage_public(s) for s in b.stages.all()]
    contestants = [
        contestant_public(bc) for bc in b.bracket_contestants.select_related("contestant")
    ]
    out = bracket_summary(b)
    out["stages"] = stages
    out["contestants"] = contestants
    return out


def user_bracket_summary(ub: UserBracket) -> dict[str, Any]:
    return {
        "id": ub.id,
        "bracket_id": ub.bracket_id,
        "user_id": ub.user_id,
        "challenge_id": ub.challenge_id,
        "is_master": ub.is_master,
        "created_at": ub.created_at.isoformat(),
    }


def user_bracket_detail(ub: UserBracket) -> dict[str, Any]:
    matchups = (
        ub.matchup_set.select_related(
            "stage",
            "contestant1",
            "contestant1__contestant",
            "contestant2",
            "contestant2__contestant",
            "winner",
            "winner__contestant",
        )
        .order_by("stage__order", "position")
    )

    by_stage: dict[int, list[dict[str, Any]]] = {}
    for m in matchups:
        by_stage.setdefault(m.stage_id, []).append(matchup_public(m))

    stages_order = list(
        ub.bracket.stages.order_by("order").values_list("id", flat=True)
    )
    matchups_by_stage = [
        {"stage_id": sid, "matchups": by_stage.get(sid, [])} for sid in stages_order
    ]

    out = user_bracket_summary(ub)
    out["bracket"] = bracket_summary(ub.bracket)
    out["matchups_by_stage"] = matchups_by_stage
    out["score_vs_master"] = None if ub.is_master else ub.calculate_score()
    return out


def auth_user(u) -> dict[str, Any]:
    return {"id": u.id, "username": u.username}
