"""Knockout pick rules and phase labels (no streak_knockout imports)."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from django.utils import timezone

from brackets.models import (
    StreakChallenge,
    StreakKnockout,
    StreakParticipant,
    StreakQuestion,
)


def bracket_qualifier_count(participant_count: int) -> int:
    if participant_count < 2:
        return participant_count
    return 2 ** int(math.floor(math.log2(participant_count)))


def knockout_round_label(round_index: int, total_rounds: int) -> str:
    if round_index == total_rounds:
        return "Final"
    if round_index == total_rounds - 1:
        return "Semi Final"
    if round_index == total_rounds - 2 and total_rounds >= 3:
        return "Quarter Final"
    return f"Round {round_index}"


def knockout_total_rounds(participant_count: int) -> int:
    bracket_size = bracket_qualifier_count(max(participant_count, 2))
    if bracket_size < 2:
        return 0
    return int(math.log2(bracket_size))


def _parse_stored_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def round_start_at(challenge: StreakChallenge, round_index: int) -> datetime | None:
    if round_index <= 1:
        return streak_season_cutoff_at(challenge)
    return _parse_stored_dt((challenge.knockout_round_starts or {}).get(str(round_index)))


def headstart_for_round(challenge: StreakChallenge, round_index: int) -> bool:
    raw = (challenge.knockout_round_headstart or {}).get(str(round_index))
    if raw is None:
        return True
    return bool(raw)


def will_be_knockout_at(challenge: StreakChallenge, when: datetime) -> bool:
    if challenge.is_knockout:
        return True
    transition = challenge.knockout_transition_at
    if transition is None:
        return False
    if timezone.is_naive(when):
        when = timezone.make_aware(when)
    if timezone.is_naive(transition):
        transition = timezone.make_aware(transition)
    return when >= transition


def streak_season_cutoff_at(challenge: StreakChallenge) -> datetime | None:
    """Exclusive boundary: picks before this time are streak season."""
    if challenge.knockout_transition_at is not None:
        return challenge.knockout_transition_at
    if not challenge.is_knockout:
        return None
    return (
        StreakKnockout.objects.filter(streak_challenge_id=challenge.id)
        .values_list("started_at", flat=True)
        .first()
    )


def participant_in_knockout_bracket_at(
    participant: StreakParticipant,
    closes_at: datetime,
) -> bool:
    challenge = participant.streak_challenge
    if not challenge.is_knockout:
        return False
    cutoff = streak_season_cutoff_at(challenge)
    if cutoff is None:
        return False
    if timezone.is_naive(closes_at):
        closes_at = timezone.make_aware(closes_at)
    if timezone.is_naive(cutoff):
        cutoff = timezone.make_aware(cutoff)
    if closes_at < cutoff:
        return False
    if participant.bracket_eliminated_at is not None:
        eliminated = participant.bracket_eliminated_at
        if timezone.is_naive(eliminated):
            eliminated = timezone.make_aware(eliminated)
        if closes_at >= eliminated:
            return False
        return True
    return participant.in_knockout_bracket


def is_knockout_pick(challenge: StreakChallenge, question: StreakQuestion) -> bool:
    if challenge.is_knockout:
        return True
    return will_be_knockout_at(challenge, question.closes_at)


def question_visible_in_challenge(
    challenge: StreakChallenge, question: StreakQuestion
) -> bool:
    if not question.knockout_only:
        return True
    return will_be_knockout_at(challenge, question.closes_at)


def knockout_phase_for_closes_at(
    challenge: StreakChallenge,
    closes_at: datetime,
    participant_count: int,
) -> dict[str, Any] | None:
    if not will_be_knockout_at(challenge, closes_at):
        return None
    total_rounds = knockout_total_rounds(participant_count)
    if total_rounds == 0:
        return None
    if timezone.is_naive(closes_at):
        closes_at = timezone.make_aware(closes_at)

    for round_index in range(total_rounds, 0, -1):
        starts_at = round_start_at(challenge, round_index)
        if starts_at is None:
            continue
        if timezone.is_naive(starts_at):
            starts_at = timezone.make_aware(starts_at)
        if closes_at >= starts_at:
            return {
                "round_index": round_index,
                "label": knockout_round_label(round_index, total_rounds),
                "starts_at": starts_at,
            }
    return None


def knockout_phases_payload(
    challenge: StreakChallenge, participant_count: int
) -> list[dict[str, Any]]:
    if challenge.knockout_transition_at is None:
        return []
    total_rounds = knockout_total_rounds(participant_count)
    if total_rounds == 0:
        return []

    rows: list[dict[str, Any]] = []
    for round_index in range(1, total_rounds + 1):
        starts_at = round_start_at(challenge, round_index)
        if starts_at is None:
            continue
        rows.append(
            {
                "round_index": round_index,
                "label": knockout_round_label(round_index, total_rounds),
                "starts_at": starts_at.isoformat(),
                "headstart_enabled": headstart_for_round(challenge, round_index),
            }
        )
    return rows


def validate_knockout_schedule(
    challenge: StreakChallenge,
    *,
    transition_at: datetime,
    round_starts: dict[str, str],
    participant_count: int,
) -> str | None:
    if challenge.is_knockout:
        return "Knockout has already started"
    if challenge.streak_competition.ended_at is not None:
        return "Competition has ended"

    total_rounds = knockout_total_rounds(participant_count)
    if total_rounds == 0:
        return "At least two participants are required to schedule knockout"

    prev = transition_at
    for round_index in range(2, total_rounds + 1):
        raw = round_starts.get(str(round_index))
        if not raw:
            return f"Start time for {knockout_round_label(round_index, total_rounds)} is required"
        starts_at = _parse_stored_dt(raw)
        if starts_at is None:
            return f"Invalid start time for {knockout_round_label(round_index, total_rounds)}"
        if starts_at <= prev:
            return "Knockout round times must be in ascending order"
        prev = starts_at
    return None
