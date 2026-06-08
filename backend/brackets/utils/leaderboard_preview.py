"""Top-N leaderboard rows for challenge list tiles."""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch

from brackets.models import BracketChallenge, Matchup, StreakChallenge, StreakParticipant, UserBracket
from brackets.utils.challenge_types import uses_prediction_scoring
from brackets.utils.leaderboard_scoring import (
    LeaderboardScoringContext,
    load_leaderboard_scoring_context,
    total_score_for_user_bracket,
)


def _preview_row(
    display_name: str,
    *,
    rank: int,
    points: int,
    points_label: str | None = None,
    is_viewer: bool = False,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "rank": rank,
        "display_name": display_name,
        "points": points,
        "is_viewer": is_viewer,
    }
    if points_label is not None:
        row["points_label"] = points_label
    return row


def _competition_ranks(scores: list[int]) -> list[int]:
    ranks: list[int] = []
    for i, score in enumerate(scores):
        if i == 0:
            ranks.append(1)
        elif score == scores[i - 1]:
            ranks.append(ranks[-1])
        else:
            ranks.append(i + 1)
    return ranks


def _assemble_preview(
    ranked: list[dict[str, Any]],
    user,
    *,
    limit: int = 3,
) -> dict[str, Any]:
    if not ranked:
        return {"top": [], "viewer": None, "gap_before_viewer": False}

    scores = [int(r["points"]) for r in ranked]
    ranks = _competition_ranks(scores)
    for i, row in enumerate(ranked):
        row["rank"] = ranks[i]
        row["is_viewer"] = (
            user is not None and row.get("user_id") == getattr(user, "id", None)
        )

    top = [
        _preview_row(
            row["display_name"],
            rank=row["rank"],
            points=row["points"],
            points_label=row.get("points_label"),
            is_viewer=row["is_viewer"],
        )
        for row in ranked[:limit]
    ]

    viewer_row: dict[str, Any] | None = None
    gap = False
    if user is not None:
        viewer_candidates = [r for r in ranked if r.get("user_id") == user.id]
        viewer_in_top = any(r.get("user_id") == user.id for r in ranked[:limit])
        if viewer_candidates and not viewer_in_top:
            best = min(viewer_candidates, key=lambda r: r["rank"])
            viewer_row = _preview_row(
                best["display_name"],
                rank=best["rank"],
                points=best["points"],
                points_label=best.get("points_label"),
                is_viewer=True,
            )
            gap = best["rank"] > limit + 1

    return {
        "top": top,
        "viewer": viewer_row,
        "gap_before_viewer": gap,
    }


def _streak_display(streak_signed: int) -> str:
    if streak_signed > 0:
        return f"{streak_signed}W"
    if streak_signed < 0:
        return f"{-streak_signed}L"
    return "—"


def streak_participant_sort_key(p: StreakParticipant) -> tuple:
    answered = p.wins + p.losses
    rate = p.wins / answered if answered else 0.0
    return (p.streak_signed, p.best_win_streak, p.wins, rate)


def bracket_challenge_leaderboard_preview(
    challenge: BracketChallenge,
    user=None,
    *,
    limit: int = 3,
    scoring_context: LeaderboardScoringContext | None = None,
) -> dict[str, Any]:
    if not uses_prediction_scoring(challenge.instance_type):
        return {"top": [], "viewer": None, "gap_before_viewer": False}

    ctx = scoring_context or load_leaderboard_scoring_context(challenge.bracket)
    if not ctx.master:
        return {"top": [], "viewer": None, "gap_before_viewer": False}

    matchup_prefetch = Prefetch(
        "matchup_set",
        queryset=Matchup.objects.select_related(
            "winner__contestant",
            "contestant1__contestant",
            "contestant2__contestant",
            "stage",
        ),
    )
    ranked: list[dict[str, Any]] = []
    for ub in (
        UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            submitted_at__isnull=False,
        )
        .select_related("user", "bracket")
        .prefetch_related(matchup_prefetch)
    ):
        score = total_score_for_user_bracket(ub, ctx)
        if score is None:
            continue
        name = (ub.display_name or "").strip() or ub.user.username
        ranked.append(
            {
                "user_id": ub.user_id,
                "display_name": name,
                "points": score,
            }
        )

    ranked.sort(
        key=lambda r: (-r["points"], r["display_name"].casefold()),
    )
    return _assemble_preview(ranked, user, limit=limit)


def streak_challenge_leaderboard_preview(
    challenge: StreakChallenge,
    user=None,
    *,
    limit: int = 3,
) -> dict[str, Any]:
    participants = list(
        StreakParticipant.objects.filter(streak_challenge=challenge).select_related(
            "user"
        )
    )
    participants.sort(key=streak_participant_sort_key, reverse=True)
    ranked = [
        {
            "user_id": p.user_id,
            "display_name": p.user.username,
            "points": p.streak_signed,
            "points_label": _streak_display(p.streak_signed),
        }
        for p in participants
    ]
    return _assemble_preview(ranked, user, limit=limit)
