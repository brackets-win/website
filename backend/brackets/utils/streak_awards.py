"""Award winners for a completed streak challenge pool."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from brackets.api import serializers
from brackets.models import (
    StreakChallenge,
    StreakKnockout,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
)
from brackets.utils.leaderboard_preview import (
    streak_participant_label,
    streak_ranked_participants,
    streak_win_rate,
)
from brackets.utils.streak_deadlines import closes_at_key
from brackets.utils.streak_scoring import _apply_batch, _is_correct


def _long_win_display(value: int) -> str:
    if value <= 0:
        return "—"
    return serializers.streak_display(value)


def _long_loss_display(value: int) -> str:
    if value <= 0:
        return "—"
    return f"{value}L"


def _award_person(p: StreakParticipant) -> dict:
    return {
        "user_id": p.user_id,
        "username": p.user.username,
        "display_name": streak_participant_label(p),
    }


def _empty_awards() -> dict:
    return {
        "streak_champion": {"winners": []},
        "best_streak": {"winners": []},
        "consolation_champion": {"winners": []},
        "best_picker": {"winners": []},
        "most_wins": {"winners": []},
        "active_streak": {"winners": []},
        "losing_streak": {"winners": []},
        "nicest_question": {"winners": []},
        "meanest_question": {"winners": []},
        "streak_ending_question": {"winners": []},
        "had_knockout": False,
    }


def _frozen_win_rate(p: StreakParticipant) -> float:
    answered = p.frozen_wins + p.frozen_losses
    return round(p.frozen_wins / answered, 4) if answered else 0.0


def _person_awards(
    participants: list[StreakParticipant],
    *,
    challenge: StreakChallenge,
    knockout: StreakKnockout | None,
) -> dict:
    had_knockout = knockout is not None

    if had_knockout:
        champions = [knockout.champion] if knockout.champion else []
        best_streak_candidates = [p for p in participants if p.frozen_best_win_streak > 0]
        if best_streak_candidates:
            max_streak = max(p.frozen_best_win_streak for p in best_streak_candidates)
            best_streak = [
                p for p in best_streak_candidates if p.frozen_best_win_streak == max_streak
            ]
        else:
            best_streak = []

        consolation = [
            p
            for p in participants
            if p.consolation_wins + p.consolation_losses > 0
            and (knockout.champion_id is None or p.id != knockout.champion_id)
        ]
        if consolation:
            max_consolation_wins = max(p.consolation_wins for p in consolation)
            consolation_winners = [
                p for p in consolation if p.consolation_wins == max_consolation_wins
            ]
        else:
            consolation_winners = []

        answered = [p for p in participants if p.frozen_wins + p.frozen_losses > 0]
        if answered:
            max_rate = max(_frozen_win_rate(p) for p in answered)
            best_pickers = [p for p in answered if _frozen_win_rate(p) == max_rate]
        else:
            best_pickers = []

        max_wins = max((p.frozen_wins for p in participants), default=0)
        most_wins = [p for p in participants if p.frozen_wins == max_wins]

        active_positive = [p for p in participants if p.frozen_streak_signed > 0]
        if active_positive:
            max_active = max(p.frozen_streak_signed for p in active_positive)
            active = [p for p in active_positive if p.frozen_streak_signed == max_active]
        else:
            active = []

        with_loss_streak = [p for p in participants if p.frozen_best_loss_streak > 0]
        if with_loss_streak:
            max_loss = max(p.frozen_best_loss_streak for p in with_loss_streak)
            losing = [
                p for p in with_loss_streak if p.frozen_best_loss_streak == max_loss
            ]
        else:
            losing = []

        return {
            "had_knockout": True,
            "streak_champion": {
                "winners": [{**_award_person(p)} for p in champions if p],
            },
            "best_streak": {
                "winners": [
                    {
                        **_award_person(p),
                        "long_win_display": _long_win_display(p.frozen_best_win_streak),
                        "best_win_streak": p.frozen_best_win_streak,
                    }
                    for p in best_streak
                ],
            },
            "consolation_champion": {
                "winners": [
                    {
                        **_award_person(p),
                        "wins": p.consolation_wins,
                        "record": f"{p.consolation_wins}-{p.consolation_losses}",
                    }
                    for p in consolation_winners
                ],
            },
            "best_picker": {
                "winners": [
                    {
                        **_award_person(p),
                        "win_pct": round(_frozen_win_rate(p) * 100),
                    }
                    for p in best_pickers
                ],
            },
            "most_wins": {
                "winners": [{**_award_person(p), "wins": p.frozen_wins} for p in most_wins],
            },
            "active_streak": {
                "winners": [
                    {
                        **_award_person(p),
                        "current_display": serializers.streak_display(
                            p.frozen_streak_signed
                        ),
                        "streak_signed": p.frozen_streak_signed,
                    }
                    for p in active
                ],
            },
            "losing_streak": {
                "winners": [
                    {
                        **_award_person(p),
                        "long_loss_display": _long_loss_display(p.frozen_best_loss_streak),
                        "best_loss_streak": p.frozen_best_loss_streak,
                    }
                    for p in losing
                ],
            },
        }

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

    with_loss_streak = [p for p in participants if p.best_loss_streak > 0]
    if with_loss_streak:
        max_loss = max(p.best_loss_streak for p in with_loss_streak)
        losing = [p for p in with_loss_streak if p.best_loss_streak == max_loss]
    else:
        losing = []

    return {
        "had_knockout": False,
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
        "best_streak": {"winners": []},
        "consolation_champion": {"winners": []},
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
            "winners": [{**_award_person(p), "wins": p.wins} for p in most_wins],
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
        "losing_streak": {
            "winners": [
                {
                    **_award_person(p),
                    "long_loss_display": _long_loss_display(p.best_loss_streak),
                    "best_loss_streak": p.best_loss_streak,
                }
                for p in losing
            ],
        },
    }


def _resolved_questions(challenge: StreakChallenge) -> list[StreakQuestion]:
    return list(
        StreakQuestion.objects.filter(
            streak_competition_id=challenge.streak_competition_id,
            resolved_at__isnull=False,
            correct_choice_id__isnull=False,
        )
        .prefetch_related("choices")
        .order_by("closes_at", "order", "id")
    )


def _choice_counts(
    challenge: StreakChallenge, question_ids: list[int]
) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for row in StreakPick.objects.filter(
        streak_challenge=challenge,
        question_id__in=question_ids,
    ).values("question_id", "choice_id"):
        counts[(row["question_id"], row["choice_id"])] += 1
    return counts


def _question_payload(
    q: StreakQuestion, counts: dict[tuple[int, int], int]
) -> dict:
    choices = list(q.choices.all())
    total = sum(counts.get((q.id, c.id), 0) for c in choices)
    choice_rows = []
    for c in choices:
        count = counts.get((q.id, c.id), 0)
        choice_rows.append(
            {
                "id": c.id,
                "label": c.label,
                "pick_count": count,
                "pick_pct": round(count * 100 / total) if total else 0,
            }
        )
    return {
        "question_id": q.id,
        "text": q.text,
        "closes_at": q.closes_at.isoformat(),
        "correct_choice_id": q.correct_choice_id,
        "choices": choice_rows,
    }


def _streak_ending_events(
    challenge: StreakChallenge,
    questions: list[StreakQuestion],
    *,
    before: datetime | None = None,
) -> list[tuple[int, int, int]]:
    """Return (user_id, question_id, broken_win_streak) for each streak break."""
    if before is not None:
        questions = [q for q in questions if q.closes_at < before]
    question_ids = [q.id for q in questions]
    picks_by_user: dict[int, dict[int, StreakPick]] = defaultdict(dict)
    for p in StreakPick.objects.filter(
        streak_challenge=challenge,
        question_id__in=question_ids,
    ).select_related("choice"):
        picks_by_user[p.user_id][p.question_id] = p

    events: list[tuple[int, int, int]] = []
    for user_id, picks_by_q in picks_by_user.items():
        # At most one scored pick per deadline; prefer lowest order on dupes.
        deadline_pick: dict[datetime, tuple[StreakQuestion, StreakPick]] = {}
        for q in questions:
            pick = picks_by_q.get(q.id)
            if pick is None:
                continue
            key = closes_at_key(q.closes_at)
            prev = deadline_pick.get(key)
            if prev is None or (q.order, q.id) < (prev[0].order, prev[0].id):
                deadline_pick[key] = (q, pick)

        streak_signed = 0
        for closes_at in sorted(deadline_pick.keys()):
            q, pick = deadline_pick[closes_at]
            previous = streak_signed
            if _is_correct(pick, q):
                streak_signed = _apply_batch(streak_signed, 1, 0)
            else:
                streak_signed = _apply_batch(streak_signed, 0, 1)
                if previous > 0:
                    events.append((user_id, q.id, previous))
    return events


def _question_awards(
    challenge: StreakChallenge,
    participants: list[StreakParticipant],
    *,
    knockout: StreakKnockout | None = None,
) -> dict:
    questions = _resolved_questions(challenge)
    if not questions:
        return {
            "nicest_question": {"winners": []},
            "meanest_question": {"winners": []},
            "streak_ending_question": {"winners": []},
        }

    question_ids = [q.id for q in questions]
    counts = _choice_counts(challenge, question_ids)
    q_by_id = {q.id: q for q in questions}

    correct_count: dict[int, int] = {}
    incorrect_count: dict[int, int] = {}
    for q in questions:
        for c in q.choices.all():
            n = counts.get((q.id, c.id), 0)
            if c.id == q.correct_choice_id:
                correct_count[q.id] = correct_count.get(q.id, 0) + n
            else:
                incorrect_count[q.id] = incorrect_count.get(q.id, 0) + n

    nicest = []
    answered_correct = {qid: n for qid, n in correct_count.items() if n > 0}
    if answered_correct:
        max_correct = max(answered_correct.values())
        nicest = [
            {**_question_payload(q_by_id[qid], counts), "correct_count": n}
            for qid, n in answered_correct.items()
            if n == max_correct
        ]

    meanest = []
    answered_incorrect = {qid: n for qid, n in incorrect_count.items() if n > 0}
    if answered_incorrect:
        max_incorrect = max(answered_incorrect.values())
        meanest = [
            {**_question_payload(q_by_id[qid], counts), "incorrect_count": n}
            for qid, n in answered_incorrect.items()
            if n == max_incorrect
        ]

    person_by_user = {p.user_id: _award_person(p) for p in participants}
    before = knockout.started_at if knockout is not None else None
    events = _streak_ending_events(challenge, questions, before=before)
    streak_ending = []
    if events:
        max_broken = max(broken for _user, _q, broken in events)
        for user_id, question_id, broken in events:
            if broken != max_broken:
                continue
            streak_ending.append(
                {
                    **_question_payload(q_by_id[question_id], counts),
                    "player": person_by_user.get(user_id),
                    "broken_win_streak": broken,
                    "long_win_display": _long_win_display(broken),
                }
            )

    def sort_key(row: dict) -> tuple:
        return (row["question_id"], (row.get("player") or {}).get("user_id", 0))

    return {
        "nicest_question": {"winners": sorted(nicest, key=sort_key)},
        "meanest_question": {"winners": sorted(meanest, key=sort_key)},
        "streak_ending_question": {"winners": sorted(streak_ending, key=sort_key)},
    }


def compute_streak_awards(
    challenge: StreakChallenge, participants: list[StreakParticipant]
) -> dict:
    if not participants:
        return _empty_awards()

    knockout = None
    try:
        knockout = challenge.knockout
    except StreakKnockout.DoesNotExist:
        pass

    person = _person_awards(participants, challenge=challenge, knockout=knockout)
    question = _question_awards(challenge, participants, knockout=knockout)
    return {**person, **question}
