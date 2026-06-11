"""Award winners for a completed streak challenge pool."""

from __future__ import annotations

from brackets.api import serializers
from brackets.models import StreakParticipant
from brackets.utils.leaderboard_preview import (
    streak_participant_label,
    streak_ranked_participants,
    streak_win_rate,
)


def _long_win_display(value: int) -> str:
    if value <= 0:
        return "—"
    return serializers.streak_display(value)


def _award_person(p: StreakParticipant) -> dict:
    return {
        "user_id": p.user_id,
        "username": p.user.username,
        "display_name": streak_participant_label(p),
    }


def compute_streak_awards(participants: list[StreakParticipant]) -> dict:
    empty = {
        "streak_champion": {"winners": []},
        "best_picker": {"winners": []},
        "most_wins": {"winners": []},
        "active_streak": {"winners": []},
    }
    if not participants:
        return empty

    champions = [p for p, rank in streak_ranked_participants(participants) if rank == 1]

    answered = [p for p in participants if p.wins + p.losses > 0]
    if answered:
        max_rate = max(streak_win_rate(p) for p in answered)
        best_pickers = [p for p in answered if streak_win_rate(p) == max_rate]
    else:
        best_pickers = []

    max_wins = max(p.wins for p in participants)
    most_wins = [p for p in participants if p.wins == max_wins]

    active_positive = [p for p in participants if p.streak_signed > 0]
    if active_positive:
        max_active = max(p.streak_signed for p in active_positive)
        active = [p for p in active_positive if p.streak_signed == max_active]
    else:
        active = []

    return {
        "streak_champion": {
            "winners": [
                {
                    **_award_person(p),
                    "long_win_display": _long_win_display(p.best_win_streak),
                    "best_win_streak": p.best_win_streak,
                }
                for p in champions
            ],
        },
        "best_picker": {
            "winners": [
                {
                    **_award_person(p),
                    "win_pct": round(streak_win_rate(p) * 100),
                }
                for p in best_pickers
            ],
        },
        "most_wins": {
            "winners": [
                {**_award_person(p), "wins": p.wins} for p in most_wins
            ],
        },
        "active_streak": {
            "winners": [
                {
                    **_award_person(p),
                    "current_display": serializers.streak_display(p.streak_signed),
                    "streak_signed": p.streak_signed,
                }
                for p in active
            ],
        },
    }
