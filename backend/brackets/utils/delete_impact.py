"""Counts of related rows removed when admin deletes catalog objects."""

from __future__ import annotations

from typing import Any

from brackets.models import (
    ActivityLog,
    Bracket,
    BracketChallenge,
    BracketContestant,
    BracketStage,
    BracketTemplate,
    ChallengeParticipant,
    Contestant,
    StreakChallenge,
    StreakCompetition,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
    StreakQuestionChoice,
    User,
    UserBracket,
)


def _items(pairs: list[tuple[str, int]]) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in pairs if count > 0]


def bracket_delete_impact(bracket: Bracket) -> list[dict[str, Any]]:
    challenge_ids = list(
        BracketChallenge.objects.filter(bracket=bracket).values_list("id", flat=True)
    )
    participant_count = (
        ChallengeParticipant.objects.filter(challenge_id__in=challenge_ids).count()
        if challenge_ids
        else 0
    )
    return _items(
        [
            ("bracket challenges", len(challenge_ids)),
            ("challenge participants", participant_count),
            ("user brackets", UserBracket.objects.filter(bracket=bracket).count()),
            (
                "contestant slots",
                BracketContestant.objects.filter(bracket=bracket).count(),
            ),
            ("stages", BracketStage.objects.filter(bracket=bracket).count()),
        ]
    )


def streak_competition_delete_impact(
    competition: StreakCompetition,
) -> list[dict[str, Any]]:
    challenge_ids = list(
        competition.challenges.values_list("id", flat=True)
    )
    return _items(
        [
            ("streak challenges", len(challenge_ids)),
            ("questions", competition.questions.count()),
            (
                "participants",
                StreakParticipant.objects.filter(
                    streak_challenge_id__in=challenge_ids
                ).count()
                if challenge_ids
                else 0,
            ),
            (
                "picks",
                StreakPick.objects.filter(
                    question__streak_competition_id=competition.id
                ).count(),
            ),
        ]
    )


def contestant_delete_impact(contestant: Contestant) -> list[dict[str, Any]]:
    return _items(
        [
            (
                "bracket assignments",
                BracketContestant.objects.filter(contestant_id=contestant.id).count(),
            ),
        ]
    )


def streak_question_delete_impact(question: StreakQuestion) -> list[dict[str, Any]]:
    return _items(
        [
            ("answer choices", StreakQuestionChoice.objects.filter(question=question).count()),
            ("picks", StreakPick.objects.filter(question=question).count()),
        ]
    )


def user_delete_impact(user: User) -> list[dict[str, Any]]:
    return _items(
        [
            ("user brackets", UserBracket.objects.filter(user=user).count()),
            (
                "challenge entries",
                ChallengeParticipant.objects.filter(user=user).count(),
            ),
            (
                "streak participations",
                StreakParticipant.objects.filter(user=user).count(),
            ),
            ("streak picks", StreakPick.objects.filter(user=user).count()),
            ("activity log rows", ActivityLog.objects.filter(user=user).count()),
            ("brackets created", Bracket.objects.filter(created_by=user).count()),
            (
                "bracket challenges created",
                BracketChallenge.objects.filter(created_by=user).count(),
            ),
            (
                "streak challenges created",
                StreakChallenge.objects.filter(created_by=user).count(),
            ),
            ("contestants created", Contestant.objects.filter(created_by=user).count()),
            (
                "bracket templates created",
                BracketTemplate.objects.filter(created_by=user).count(),
            ),
        ]
    )
