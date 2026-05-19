"""Serialize domain models to JSON-friendly dicts for API responses."""

from __future__ import annotations

from typing import Any

from brackets.models import (
    Bracket,
    BracketChallenge,
    BracketContestant,
    BracketStage,
    BracketTemplate,
    Contestant,
    GroupStage,
    KnockoutStage,
    Matchup,
    UserBracket,
)
from brackets.utils.bracket_completeness import user_bracket_is_complete
from brackets.utils.challenge_deadline import deadline_passed


def contestant_public(bc: BracketContestant) -> dict[str, Any]:
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
        "id": bc.id,
        "display_name": name,
        "seed": bc.seed,
        "contestant_id": bc.contestant_id,
        "image_url": img,
    }


def stage_public(stage: BracketStage) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": stage.id,
        "name": stage.name,
        "order": stage.order,
        "stage_type": stage.stage_type,
        "number_of_contestants": stage.number_of_contestants,
        "contestants_advancing": stage.contestants_advancing,
        "is_random_draw": stage.is_random_draw,
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
            "is_third_place": ks.is_third_place,
            "number_of_legs": ks.number_of_legs,
            "has_extra_time": ks.has_extra_time,
            "has_penalty_shootout": ks.has_penalty_shootout,
        }
    elif stage.stage_type == BracketStage.StageType.GROUP:
        gs = GroupStage.objects.get(pk=stage.pk)
        base["group"] = {
            "number_of_groups": gs.number_of_groups,
            "matches_per_contestant": gs.matches_per_contestant,
            "contestants_qualifying_per_group": gs.contestants_qualifying_per_group,
            "remaining_spots_strategy": gs.remaining_spots_strategy,
            "points_per_win": gs.points_per_win,
            "points_per_tie": gs.points_per_tie,
            "points_per_loss": gs.points_per_loss,
            "ties_allowed": gs.ties_allowed,
        }
    return base


def bracket_groups_preview(b: Bracket) -> list[dict[str, Any]]:
    """
    Split bracket contestants evenly into labeled groups (A, B, …) for UI when
    no ``Group`` rows exist yet — same ordering as seed (seed order).
    """
    stage = (
        b.stages.filter(stage_type=BracketStage.StageType.GROUP)
        .order_by("order")
        .first()
    )
    if stage is None:
        return []
    gs = GroupStage.objects.get(pk=stage.pk)
    n_groups = gs.number_of_groups
    contestants = list(
        b.bracket_contestants.select_related("contestant").order_by("seed", "id")
    )
    if not contestants:
        return []
    if len(contestants) % n_groups != 0:
        return []
    per = len(contestants) // n_groups
    out: list[dict[str, Any]] = []
    for i in range(n_groups):
        chunk = contestants[i * per : (i + 1) * per]
        code = chr(65 + i) if i < 26 else str(i + 1)
        out.append(
            {
                "code": code,
                "stage_id": stage.id,
                "teams": [contestant_public(c) for c in chunk],
            }
        )
    return out


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


def bracket_image_url(b: Bracket, request=None) -> str | None:
    if not b.image:
        return None
    return b.image.url


def bracket_summary(b: Bracket, request=None) -> dict[str, Any]:
    challenge_count = getattr(b, "challenge_count", None)
    if challenge_count is None:
        challenge_count = b.bracketchallenge_set.count()
    return {
        "id": b.id,
        "identifier": b.identifier,
        "name": b.name,
        "description": b.description,
        "image_url": bracket_image_url(b, request),
        "created_at": b.created_at.isoformat(),
        "randomize_seeds_per_challenge": b.randomize_seeds_per_challenge,
        "has_third_place_match": b.has_third_place_match,
        "show_seeds": b.show_seeds,
        "metadata": b.metadata,
        "challenge_count": challenge_count,
    }


def bracket_detail(
    b: Bracket, *, master_user_bracket_id: int | None = None, request=None
) -> dict[str, Any]:
    stages = [stage_public(s) for s in b.stages.all()]
    contestants = [
        contestant_public(bc) for bc in b.bracket_contestants.select_related("contestant")
    ]
    out = bracket_summary(b, request)
    out["stages"] = stages
    out["contestants"] = contestants
    out["groups"] = bracket_groups_preview(b)
    if master_user_bracket_id is not None:
        out["master_user_bracket_id"] = master_user_bracket_id
    return out


def user_bracket_summary(ub: UserBracket) -> dict[str, Any]:
    complete, _ = user_bracket_is_complete(ub)
    can_edit = not ub.is_master and ub.submitted_at is None
    if can_edit and ub.challenge_id:
        ch = ub.challenge
        if ch and deadline_passed(ch):
            can_edit = False
    return {
        "id": ub.id,
        "bracket_id": ub.bracket_id,
        "user_id": ub.user_id,
        "challenge_id": ub.challenge_id,
        "is_master": ub.is_master,
        "created_at": ub.created_at.isoformat(),
        "submitted_at": (
            ub.submitted_at.isoformat() if ub.submitted_at else None
        ),
        "is_complete": complete,
        "can_edit": can_edit,
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
    out["metadata"] = ub.metadata if isinstance(ub.metadata, dict) else {}
    return out


def auth_user(u) -> dict[str, Any]:
    return {"id": u.id, "username": u.username, "is_staff": bool(u.is_staff)}


def contestant_tag_public(tag) -> dict[str, Any]:
    return {"id": tag.id, "name": tag.name}


def contestant_catalog(c: Contestant, request=None) -> dict[str, Any]:
    """Catalog row for admin/API."""
    out: dict[str, Any] = {
        "id": c.id,
        "identifier": c.identifier,
        "name": c.name,
        "description": c.description or "",
        "image_url": c.image_url or "",
        "metadata": c.metadata,
        "tags": [contestant_tag_public(t) for t in c.tags.all()],
    }
    if c.photo:
        out["photo_url"] = c.photo.url
    elif c.image_url:
        out["photo_url"] = c.image_url
    else:
        out["photo_url"] = None
    return out


def challenge_summary(
    c: BracketChallenge,
    *,
    user_bracket_id: int | None = None,
    user_bracket: UserBracket | None = None,
    request=None,
) -> dict[str, Any]:
    passed = deadline_passed(c)
    ub = user_bracket
    submitted = ub is not None and ub.submitted_at is not None
    complete = False
    if ub is not None:
        complete, _ = user_bracket_is_complete(ub)
    can_join = c.instance_type == "CHALLENGE" and not passed
    can_edit = (
        ub is not None
        and not submitted
        and not passed
        and ub.submitted_at is None
    )
    return {
        "id": c.id,
        "name": c.name,
        "bracket_id": c.bracket_id,
        "bracket_name": c.bracket.name,
        "bracket_image_url": bracket_image_url(c.bracket, request),
        "instance_type": c.instance_type,
        "is_public": c.is_public,
        "is_private": not c.is_public,
        "join_code": c.join_code if not c.is_public else None,
        "submission_deadline": (
            c.submission_deadline.isoformat()
            if c.submission_deadline
            else None
        ),
        "deadline_passed": passed,
        "user_bracket_id": user_bracket_id,
        "is_submitted": submitted,
        "is_complete": complete,
        "can_join": can_join,
        "can_edit_picks": can_edit,
    }


def leaderboard_column(*, key: str, name: str) -> dict[str, Any]:
    return {"key": key, "name": name}


def leaderboard_entry(
    *,
    username: str,
    user_bracket_id: int,
    score: int | None,
    stage_scores: dict[str, int | None],
    submitted_at,
) -> dict[str, Any]:
    return {
        "username": username,
        "user_bracket_id": user_bracket_id,
        "score": score,
        "stage_scores": stage_scores,
        "submitted_at": (
            submitted_at.isoformat() if submitted_at else None
        ),
    }


def bracket_template_summary(t: BracketTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "template_type": t.template_type,
        "description": t.description or "",
        "is_system": t.is_system,
    }
