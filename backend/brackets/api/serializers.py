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
from brackets.utils.group_results_mode import show_live_group_results_note_for_bracket
from brackets.utils.leaderboard_preview import bracket_challenge_leaderboard_preview
from brackets.utils.challenge_types import (
    CHALLENGE,
    POLL,
    TOURNAMENT,
    creates_user_bracket,
    uses_bracket_submission,
    uses_prediction_scoring,
)
from brackets.utils.contestant_images import resolve_contestant_image_url


def contestant_public(bc: BracketContestant) -> dict[str, Any]:
    name = bc.name_override or (
        bc.contestant.name if bc.contestant else f"Contestant {bc.id}"
    )
    c = bc.contestant
    img = resolve_contestant_image_url(c) if c else None
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
            "group_position_picking": gs.group_position_picking,
            "points_per_win": gs.points_per_win,
            "points_per_tie": gs.points_per_tie,
            "points_per_loss": gs.points_per_loss,
            "points_per_exact_position": gs.points_per_exact_position,
            "points_per_advancer": gs.points_per_advancer,
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
        b.bracket_contestants.select_related("contestant")
        .prefetch_related("contestant__tags")
        .order_by("seed", "id")
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


def streak_competition_image_url(competition, request=None) -> str | None:
    if not competition.image:
        return None
    return competition.image.url


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
        "points_champion": b.points_champion,
        "points_third_place_winner": b.points_third_place_winner,
        "show_seeds": b.show_seeds,
        "metadata": b.metadata,
        "challenge_count": challenge_count,
        "is_reusable": b.is_reusable,
    }


def bracket_detail(
    b: Bracket, *, master_user_bracket_id: int | None = None, request=None
) -> dict[str, Any]:
    stages = [stage_public(s) for s in b.stages.all()]
    contestants = [
        contestant_public(bc)
        for bc in b.bracket_contestants.select_related("contestant").prefetch_related(
            "contestant__tags"
        )
    ]
    out = bracket_summary(b, request)
    out["stages"] = stages
    out["contestants"] = contestants
    out["groups"] = bracket_groups_preview(b)
    if master_user_bracket_id is not None:
        out["master_user_bracket_id"] = master_user_bracket_id
    return out


def user_bracket_summary(ub: UserBracket, *, viewer=None) -> dict[str, Any]:
    complete, _ = user_bracket_is_complete(ub)
    # Master bracket is staff-only via API; editable regardless of challenge deadline.
    # Staff can fill participant entries past the deadline (historical import).
    if ub.is_master:
        can_edit = True
    else:
        can_edit = ub.submitted_at is None
        if can_edit and ub.challenge_id:
            ch = ub.challenge
            if ch and deadline_passed(ch):
                can_edit = bool(viewer is not None and getattr(viewer, "is_staff", False))
    return {
        "id": ub.id,
        "bracket_id": ub.bracket_id,
        "user_id": ub.user_id,
        "challenge_id": ub.challenge_id,
        "display_name": (ub.display_name or "").strip(),
        "is_master": ub.is_master,
        "created_at": ub.created_at.isoformat(),
        "submitted_at": (
            ub.submitted_at.isoformat() if ub.submitted_at else None
        ),
        "is_complete": complete,
        "can_edit": can_edit,
    }


def _show_scoring_to_viewer(ub: UserBracket, viewer, *, can_edit: bool) -> bool:
    """Score/highlights when the entry is locked, or a peer views in the same challenge."""
    if ub.is_master:
        return False
    if ub.submitted_at or not can_edit:
        return True
    return (
        viewer is not None
        and viewer.id != ub.user_id
        and _viewer_sees_scoring_highlights(viewer, ub)
    )


def user_bracket_detail(ub: UserBracket, *, viewer=None) -> dict[str, Any]:
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
        .prefetch_related(
            "contestant1__contestant__tags",
            "contestant2__contestant__tags",
            "winner__contestant__tags",
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

    out = user_bracket_summary(ub, viewer=viewer)
    out["bracket"] = bracket_summary(ub.bracket)
    out["matchups_by_stage"] = matchups_by_stage
    can_show_scoring = _show_scoring_to_viewer(
        ub, viewer, can_edit=out["can_edit"]
    )
    if ub.is_master:
        out["score_vs_master"] = None
    elif can_show_scoring:
        from brackets.utils.leaderboard_scoring import read_stored_leaderboard_scores

        out["score_vs_master"] = read_stored_leaderboard_scores(ub).score
    else:
        out["score_vs_master"] = None
    if ub.is_master:
        from brackets.utils.leaderboard_scoring import is_master_scoring_pending
        from brackets.utils.next_match import is_next_match_pending

        out["leaderboard_scores_pending"] = is_master_scoring_pending(
            ub.bracket
        ) or is_next_match_pending(ub.bracket)
    out["metadata"] = ub.metadata if isinstance(ub.metadata, dict) else {}
    if (
        viewer is not None
        and can_show_scoring
        and _viewer_sees_scoring_highlights(viewer, ub)
    ):
        from brackets.utils.scoring_highlights import scoring_highlights_for_user_bracket

        out["scoring_highlights"] = scoring_highlights_for_user_bracket(ub)
    return out


def _viewer_sees_scoring_highlights(viewer, ub: UserBracket) -> bool:
    """Own bracket or another entry in a challenge the viewer participates in."""
    if ub.user_id == viewer.id:
        return True
    if getattr(viewer, "is_staff", False):
        return True
    if ub.challenge_id is None:
        return False
    from brackets.models import ChallengeParticipant

    return ChallengeParticipant.objects.filter(
        user=viewer,
        challenge_id=ub.challenge_id,
    ).exists()


def auth_user(u) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "is_staff": bool(u.is_staff),
        "must_change_password": bool(u.must_change_password),
    }


def admin_user(u) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "is_staff": bool(u.is_staff),
        "must_change_password": bool(u.must_change_password),
        "date_joined": u.date_joined.isoformat() if u.date_joined else None,
    }


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
    out["photo_url"] = resolve_contestant_image_url(c)
    return out


def _user_entry_payload(ub: UserBracket) -> dict[str, Any]:
    complete, _ = user_bracket_is_complete(ub)
    return {
        "user_bracket_id": ub.id,
        "display_name": (ub.display_name or "").strip(),
        "is_submitted": ub.submitted_at is not None,
        "is_complete": complete,
    }


def _created_by_username(obj: BracketChallenge | Any) -> str:
    if not getattr(obj, "created_by_id", None):
        return ""
    user = getattr(obj, "created_by", None)
    if user is None:
        return ""
    return (getattr(user, "username", None) or "").strip()


def challenge_summary(
    c: BracketChallenge,
    *,
    user=None,
    user_bracket_id: int | None = None,
    user_bracket: UserBracket | None = None,
    user_entries: list[UserBracket] | None = None,
    master_user_bracket_id: int | None = None,
    can_manage_bracket: bool = False,
    request=None,
    leaderboard_preview: dict[str, Any] | None = None,
    show_outcomes_tab: bool | None = None,
) -> dict[str, Any]:
    passed = deadline_passed(c) if c.instance_type == CHALLENGE else False
    ub = user_bracket
    entries = user_entries or []
    submitted = any(e.submitted_at is not None for e in entries) or (
        ub is not None and ub.submitted_at is not None
    )
    from brackets.utils.challenge_entries import user_has_submitted_challenge

    can_view_peer_brackets = (
        user is not None
        and (
            c.instance_type != CHALLENGE
            or user_has_submitted_challenge(user, c)
        )
    )
    complete = False
    if ub is not None:
        complete, _ = user_bracket_is_complete(ub)

    instance_labels = {
        CHALLENGE: "Bracket Challenge",
        TOURNAMENT: "Tournament",
        POLL: "Poll",
    }
    needs_user_bracket = creates_user_bracket(c.instance_type)
    entry_count = len(user_entries) if user_entries is not None else (
        1 if user_bracket is not None else 0
    )

    from brackets.utils.challenge_entries import max_entries_in_use

    can_add_entry = (
        c.instance_type in (CHALLENGE, TOURNAMENT, POLL)
        and not (c.instance_type == CHALLENGE and passed)
        and entry_count < c.max_entries
    )
    tournament_team_count = None
    teams_configured = None
    if c.instance_type == TOURNAMENT:
        from brackets.utils.tournament_teams import (
            tournament_team_capacity,
            tournament_teams_public,
        )

        tournament_team_count = tournament_team_capacity(c.bracket)
        required = tournament_team_count or 0
        configured = len(tournament_teams_public(c.bracket))
        teams_configured = required > 0 and configured >= required
    is_creator = user is not None and c.created_by_id == user.id
    can_join = can_add_entry
    can_edit = False
    if ub is not None and not passed:
        if uses_bracket_submission(c.instance_type):
            can_edit = not submitted and ub.submitted_at is None
        elif c.instance_type == POLL:
            can_edit = True
    return {
        "id": c.id,
        "name": c.name,
        "created_by_username": _created_by_username(c),
        "bracket_id": c.bracket_id,
        "bracket_name": c.bracket.name,
        "bracket_image_url": bracket_image_url(c.bracket, request),
        "instance_type": c.instance_type,
        "instance_type_label": instance_labels.get(
            c.instance_type, c.instance_type
        ),
        "needs_user_bracket": needs_user_bracket,
        "uses_prediction_leaderboard": uses_prediction_scoring(c.instance_type),
        "is_public": c.is_public,
        "is_private": not c.is_public,
        "join_code": c.join_code if not c.is_public else None,
        "submission_deadline": (
            c.submission_deadline.isoformat()
            if c.instance_type == CHALLENGE and c.submission_deadline
            else None
        ),
        "deadline_passed": passed if c.instance_type == CHALLENGE else False,
        "max_entries": c.max_entries,
        "entry_count": entry_count,
        "user_bracket_id": user_bracket_id,
        "user_entries": [
            _user_entry_payload(ub) for ub in (user_entries or [])
        ],
        "is_submitted": submitted,
        "can_view_peer_brackets": can_view_peer_brackets,
        "is_complete": complete,
        "can_join": can_join,
        "can_add_entry": can_add_entry,
        "can_edit_picks": can_edit,
        "can_manage_bracket": can_manage_bracket,
        "is_creator": is_creator,
        "max_entries_minimum": (
            max_entries_in_use(c)
            if is_creator and c.instance_type == CHALLENGE
            else None
        ),
        "master_user_bracket_id": master_user_bracket_id,
        "tournament_team_count": tournament_team_count,
        "teams_configured": teams_configured,
        "leaderboard_preview": (
            leaderboard_preview
            if leaderboard_preview is not None
            else bracket_challenge_leaderboard_preview(c, user)
        ),
        "show_live_group_results_note": (
            show_live_group_results_note_for_bracket(c.bracket)
            if c.instance_type == CHALLENGE
            else False
        ),
        "show_outcomes_tab": (
            show_outcomes_tab
            if show_outcomes_tab is not None
            else (
                _show_outcomes_tab_for_challenge(c)
                if c.instance_type == CHALLENGE
                else False
            )
        ),
    }


def admin_challenge_summary(
    c: BracketChallenge,
    *,
    request=None,
    participant_count: int = 0,
    entry_count: int = 0,
) -> dict[str, Any]:
    """Catalog row for the admin Challenges tab."""
    passed = deadline_passed(c) if c.instance_type == CHALLENGE else False
    instance_labels = {
        CHALLENGE: "Bracket Challenge",
        TOURNAMENT: "Tournament",
        POLL: "Poll",
    }
    return {
        "id": c.id,
        "name": c.name,
        "created_by_username": _created_by_username(c),
        "bracket_id": c.bracket_id,
        "bracket_name": c.bracket.name,
        "bracket_image_url": bracket_image_url(c.bracket, request),
        "instance_type": c.instance_type,
        "instance_type_label": instance_labels.get(
            c.instance_type, c.instance_type
        ),
        "needs_user_bracket": creates_user_bracket(c.instance_type),
        "is_public": c.is_public,
        "is_private": not c.is_public,
        "join_code": c.join_code if not c.is_public else None,
        "submission_deadline": (
            c.submission_deadline.isoformat()
            if c.instance_type == CHALLENGE and c.submission_deadline
            else None
        ),
        "deadline_passed": passed if c.instance_type == CHALLENGE else False,
        "max_entries": c.max_entries,
        "participant_count": participant_count,
        "entry_count": entry_count,
        "max_entries_minimum": None,
    }


def _show_outcomes_tab_for_challenge(c) -> bool:
    from brackets.utils.challenge_outcomes import show_outcomes_tab_for_challenge

    return show_outcomes_tab_for_challenge(c)


def streak_display(streak_signed: int) -> str:
    if streak_signed > 0:
        return f"{streak_signed}W"
    if streak_signed < 0:
        return f"{-streak_signed}L"
    return "—"


def leaderboard_column(*, key: str, name: str) -> dict[str, Any]:
    return {"key": key, "name": name}


def leaderboard_next_match_pick(bc: BracketContestant | None) -> dict[str, Any] | None:
    if bc is None:
        return None
    name = bc.name_override or (
        bc.contestant.name if bc.contestant else f"Contestant {bc.id}"
    )
    img = resolve_contestant_image_url(bc.contestant) if bc.contestant else None
    return {
        "bracket_contestant_id": bc.id,
        "image_url": img,
        "display_name": name,
    }


def leaderboard_entry(
    *,
    username: str,
    display_name: str,
    user_bracket_id: int,
    score: int | None,
    potential: int | None,
    potential_rank: int | None,
    stage_scores: dict[str, int | None],
    top_four_picks: list[dict[str, Any] | None],
    submitted_at,
    next_match_pick: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "username": username,
        "display_name": display_name,
        "user_bracket_id": user_bracket_id,
        "score": score,
        "potential": potential,
        "potential_rank": potential_rank,
        "stage_scores": stage_scores,
        "top_four_picks": top_four_picks,
        "next_match_pick": next_match_pick,
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
        "default_number_of_contestants": t.default_number_of_contestants,
        "is_system": t.is_system,
    }
