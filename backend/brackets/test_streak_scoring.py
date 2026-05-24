"""Directional streak scoring."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
    StreakQuestionChoice,
)
from brackets.utils.streak_scoring import (
    _apply_batch,
    recalculate_participant_stats,
    resolve_question,
)

User = get_user_model()


def _make_question(competition, text, labels, *, closes_at=None, order=1):
    closes_at = closes_at or timezone.now()
    question = StreakQuestion.objects.create(
        streak_competition=competition,
        text=text,
        closes_at=closes_at,
        order=order,
    )
    choices = [
        StreakQuestionChoice.objects.create(
            question=question, label=label, order=idx
        )
        for idx, label in enumerate(labels, start=1)
    ]
    return question, choices


class StreakScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="streaker", password="x")
        self.competition = StreakCompetition.objects.create(name="Props")
        self.challenge = StreakChallenge.objects.create(
            name="Friends",
            streak_competition=self.competition,
            created_by=self.user,
            is_public=True,
        )
        self.participant = StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.user
        )
        self.closes = timezone.now()

    def test_apply_batch_mixed_resets_to_win_count(self):
        self.assertEqual(_apply_batch(2, 2, 1), 2)

    def test_apply_batch_extends_win_streak(self):
        self.assertEqual(_apply_batch(2, 2, 0), 4)

    def test_apply_batch_extends_loss_streak(self):
        self.assertEqual(_apply_batch(-1, 0, 2), -3)

    def test_recalculate_same_close_time_mixed(self):
        q1, c1 = _make_question(
            self.competition, "Q1", ["Yes", "No"], closes_at=self.closes, order=1
        )
        q2, c2 = _make_question(
            self.competition, "Q2", ["Yes", "No"], closes_at=self.closes, order=2
        )
        q1.correct_choice = c1[0]
        q1.resolved_at = timezone.now()
        q1.save(update_fields=["correct_choice", "resolved_at"])
        q2.correct_choice = c2[1]
        q2.resolved_at = timezone.now()
        q2.save(update_fields=["correct_choice", "resolved_at"])

        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q1,
            user=self.user,
            choice=c1[0],
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q2,
            user=self.user,
            choice=c1[0],
        )
        recalculate_participant_stats(self.participant)
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.streak_signed, 1)
        self.assertEqual(self.participant.wins, 1)
        self.assertEqual(self.participant.losses, 1)
        self.assertEqual(self.participant.best_win_streak, 1)

    def test_resolve_question_updates_all_linked_challenges(self):
        other = StreakChallenge.objects.create(
            name="Office",
            streak_competition=self.competition,
            created_by=self.user,
            is_public=True,
        )
        other_participant = StreakParticipant.objects.create(
            streak_challenge=other, user=self.user
        )
        q, choices = _make_question(self.competition, "Win?", ["Yes", "No"], order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q,
            user=self.user,
            choice=choices[0],
        )
        StreakPick.objects.create(
            streak_challenge=other,
            question=q,
            user=self.user,
            choice=choices[0],
        )
        resolve_question(q, choices[0].id)
        self.participant.refresh_from_db()
        other_participant.refresh_from_db()
        self.assertEqual(self.participant.streak_signed, 1)
        self.assertEqual(other_participant.streak_signed, 1)
