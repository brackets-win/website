"""One open pick per question close time (deadline slot)."""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from brackets.models import StreakChallenge, StreakPick, StreakQuestion
from brackets.utils.streak_knockout_rules import is_knockout_pick


def closes_at_key(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def open_deadline_pick_map(
    streak_challenge_id: int,
    user_id: int,
    *,
    challenge: StreakChallenge | None = None,
) -> dict[datetime, int]:
    """Map deadline -> question_id for unresolved streak-mode picks in this challenge."""
    if challenge is None:
        challenge = StreakChallenge.objects.get(pk=streak_challenge_id)
    result: dict[datetime, int] = {}
    picks = (
        StreakPick.objects.filter(
            streak_challenge_id=streak_challenge_id,
            user_id=user_id,
            question__resolved_at__isnull=True,
        )
        .select_related("question")
        .order_by("question__order", "question__id")
    )
    for pick in picks:
        if is_knockout_pick(challenge, pick.question):
            continue
        key = closes_at_key(pick.question.closes_at)
        if key not in result:
            result[key] = pick.question_id
    return result


def other_open_pick_at_same_deadline(
    challenge: StreakChallenge,
    user_id: int,
    question: StreakQuestion,
) -> StreakPick | None:
    other = (
        StreakPick.objects.filter(
            streak_challenge=challenge,
            user_id=user_id,
            question__closes_at=question.closes_at,
            question__resolved_at__isnull=True,
        )
        .exclude(question_id=question.id)
        .select_related("question")
        .first()
    )
    if other is None:
        return None
    if is_knockout_pick(challenge, question) or is_knockout_pick(
        challenge, other.question
    ):
        return None
    return other
