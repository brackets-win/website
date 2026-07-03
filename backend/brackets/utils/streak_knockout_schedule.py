"""Apply scheduled knockout transition and round advances."""

from __future__ import annotations

from django.utils import timezone

from brackets.models import StreakChallenge, StreakKnockout
from brackets.utils.streak_knockout_rules import (
    knockout_total_rounds,
    round_start_at,
)


def process_scheduled_knockout(challenge: StreakChallenge) -> None:
    """Apply due transition and round advances (call on read/write paths)."""
    if challenge.streak_competition.ended_at is not None:
        return

    now = timezone.now()

    if not challenge.is_knockout:
        transition = challenge.knockout_transition_at
        if transition is None or now < transition:
            return
        from brackets.utils.streak_knockout import start_knockout

        try:
            start_knockout(challenge)
        except ValueError:
            return
        challenge.refresh_from_db()

    try:
        knockout = challenge.knockout
    except StreakKnockout.DoesNotExist:
        return

    if knockout.status == StreakKnockout.Status.COMPLETE:
        return

    from brackets.utils.streak_knockout import advance_knockout_round

    participant_count = challenge.participants.count()
    total_rounds = knockout_total_rounds(participant_count)

    if knockout.status == StreakKnockout.Status.SETUP:
        transition = challenge.knockout_transition_at
        if transition is not None and now >= transition:
            try:
                advance_knockout_round(
                    knockout, headstart_enabled=knockout.headstart_enabled
                )
            except ValueError:
                pass
        return

    current = knockout.current_round
    if current >= total_rounds:
        return

    next_round = current + 1
    next_start = round_start_at(challenge, next_round)
    if next_start is None or now < next_start:
        return

    try:
        advance_knockout_round(knockout, headstart_enabled=knockout.headstart_enabled)
    except ValueError:
        pass
