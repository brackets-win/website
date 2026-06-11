"""Aggregate pick statistics for a streak challenge (cached per challenge)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from brackets.models import (
    StreakChallenge,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
)
from brackets.utils.leaderboard_preview import streak_participant_label

STREAK_STATS_REVISION_KEY = "streak_stats_revision"
STREAK_STATS_CACHE_KEY = "streak_stats_cache"


def get_streak_stats_revision(challenge: StreakChallenge) -> int:
    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    return int(meta.get(STREAK_STATS_REVISION_KEY) or 0)


def bump_streak_stats_revision(challenge: StreakChallenge) -> int:
    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    revision = int(meta.get(STREAK_STATS_REVISION_KEY) or 0) + 1
    meta[STREAK_STATS_REVISION_KEY] = revision
    meta.pop(STREAK_STATS_CACHE_KEY, None)
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])
    return revision


def bump_streak_stats_for_competition(streak_competition_id: int) -> None:
    for challenge in StreakChallenge.objects.filter(
        streak_competition_id=streak_competition_id
    ).only("id", "metadata"):
        bump_streak_stats_revision(challenge)


def _read_cached_stats(
    challenge: StreakChallenge, revision: int
) -> dict[str, Any] | None:
    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    cache = meta.get(STREAK_STATS_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    if cache.get("revision") != revision:
        return None
    questions = cache.get("questions")
    if not isinstance(questions, list):
        return None
    return {"questions": questions}


def _write_cached_stats(
    challenge: StreakChallenge,
    revision: int,
    stats: dict[str, Any],
) -> None:
    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    meta[STREAK_STATS_CACHE_KEY] = {
        "revision": revision,
        "questions": stats["questions"],
    }
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])


def get_streak_challenge_stats(challenge: StreakChallenge) -> dict[str, Any]:
    if challenge.pk is not None:
        challenge.refresh_from_db(fields=["metadata"])
    revision = get_streak_stats_revision(challenge)
    cached = _read_cached_stats(challenge, revision)
    if cached is not None:
        return cached
    stats = compute_streak_challenge_stats(challenge)
    _write_cached_stats(challenge, revision, stats)
    return stats


def compute_streak_challenge_stats(challenge: StreakChallenge) -> dict[str, Any]:
    competition_id = challenge.streak_competition_id
    questions = list(
        StreakQuestion.objects.filter(
            streak_competition_id=competition_id,
            resolved_at__isnull=False,
        )
        .prefetch_related("choices")
        .order_by("-closes_at", "-order", "-id")
    )
    if not questions:
        return {"questions": []}

    question_ids = [q.id for q in questions]
    participants = {
        p.user_id: streak_participant_label(p)
        for p in StreakParticipant.objects.filter(
            streak_challenge=challenge
        ).select_related("user")
    }

    pickers_by_q_choice: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(
        list
    )
    counts_by_q_choice: dict[tuple[int, int], int] = defaultdict(int)
    for row in StreakPick.objects.filter(
        streak_challenge=challenge,
        question_id__in=question_ids,
    ).values("question_id", "choice_id", "user_id"):
        key = (row["question_id"], row["choice_id"])
        counts_by_q_choice[key] += 1
        label = participants.get(row["user_id"])
        if label is not None:
            pickers_by_q_choice[key].append(
                {"user_id": row["user_id"], "display_name": label}
            )

    questions_out: list[dict[str, Any]] = []
    for q in questions:
        choice_counts = {
            choice.id: counts_by_q_choice.get((q.id, choice.id), 0)
            for choice in q.choices.all()
        }
        total = sum(choice_counts.values())
        choice_rows: list[dict[str, Any]] = []
        for choice in q.choices.all():
            count = choice_counts.get(choice.id, 0)
            pick_pct = round(count * 100 / total) if total else 0
            pickers = pickers_by_q_choice.get((q.id, choice.id), [])
            pickers.sort(key=lambda p: str(p["display_name"]).casefold())
            choice_rows.append(
                {
                    "id": choice.id,
                    "label": choice.label,
                    "pick_count": count,
                    "pick_pct": pick_pct,
                    "pickers": pickers,
                }
            )
        questions_out.append(
            {
                "question_id": q.id,
                "text": q.text,
                "closes_at": q.closes_at.isoformat(),
                "correct_choice_id": q.correct_choice_id,
                "choices": choice_rows,
            }
        )

    return {"questions": questions_out}
