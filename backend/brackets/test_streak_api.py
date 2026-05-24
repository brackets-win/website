"""API tests for streak challenges."""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
    StreakQuestionChoice,
)

User = get_user_model()


class StreakCompetitionAdminApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username="admin", password="x", is_staff=True
        )
        self.competition = StreakCompetition.objects.create(name="World Cup Props")

    def test_staff_can_patch_competition_name(self):
        self.client.force_login(self.staff)
        res = self.client.patch(
            f"/brackets/api/streak-competitions/{self.competition.id}",
            data=json.dumps({"name": "WC Props"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.name, "WC Props")

    def test_staff_can_delete_competition_without_challenges(self):
        self.client.force_login(self.staff)
        pk = self.competition.pk
        res = self.client.delete(f"/brackets/api/streak-competitions/{pk}")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(StreakCompetition.objects.filter(pk=pk).exists())

    def test_cannot_delete_competition_with_challenges(self):
        creator = User.objects.create_user(username="host", password="x")
        StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=creator,
            is_public=True,
        )
        self.client.force_login(self.staff)
        res = self.client.delete(
            f"/brackets/api/streak-competitions/{self.competition.id}"
        )
        self.assertEqual(res.status_code, 409)
        self.assertTrue(
            StreakCompetition.objects.filter(pk=self.competition.pk).exists()
        )

    def test_staff_can_create_question_with_choices(self):
        self.client.force_login(self.staff)
        res = self.client.post(
            f"/brackets/api/streak-competitions/{self.competition.id}/questions",
            data=json.dumps(
                {
                    "text": "Who wins?",
                    "closes_at": "2030-01-01T12:00:00-05:00",
                    "choices": ["Argentina", "Brazil"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        payload = res.json()["question"]
        self.assertEqual(len(payload["choices"]), 2)
        self.assertEqual(payload["choices"][0]["label"], "Argentina")

    def test_staff_can_update_and_delete_question(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Old text",
            closes_at=timezone.now() + timezone.timedelta(days=1),
            order=1,
        )
        StreakQuestionChoice.objects.create(
            question=question, label="A", order=1
        )
        StreakQuestionChoice.objects.create(
            question=question, label="B", order=2
        )
        self.client.force_login(self.staff)
        patch_res = self.client.patch(
            f"/brackets/api/streak-questions/{question.id}",
            data=json.dumps(
                {
                    "text": "New text",
                    "closes_at": "2030-06-15T20:00:00Z",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_res.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(question.text, "New text")

        delete_res = self.client.delete(
            f"/brackets/api/streak-questions/{question.id}"
        )
        self.assertEqual(delete_res.status_code, 200)
        self.assertFalse(StreakQuestion.objects.filter(pk=question.pk).exists())

    def test_staff_can_change_resolved_answer(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Winner?",
            closes_at=timezone.now() - timezone.timedelta(hours=1),
            order=1,
        )
        a = StreakQuestionChoice.objects.create(
            question=question, label="A", order=1
        )
        b = StreakQuestionChoice.objects.create(
            question=question, label="B", order=2
        )
        self.client.force_login(self.staff)
        first = self.client.post(
            f"/brackets/api/streak-questions/{question.id}/resolve",
            data=json.dumps({"correct_choice_id": a.id}),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)
        question.refresh_from_db()
        first_resolved_at = question.resolved_at

        second = self.client.post(
            f"/brackets/api/streak-questions/{question.id}/resolve",
            data=json.dumps({"correct_choice_id": b.id}),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(question.correct_choice_id, b.id)
        self.assertEqual(question.resolved_at, first_resolved_at)

    def test_staff_can_resolve_past_deadline_question(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Will it rain?",
            closes_at=timezone.now() - timezone.timedelta(hours=1),
            order=1,
        )
        yes = StreakQuestionChoice.objects.create(
            question=question, label="Yes", order=1
        )
        StreakQuestionChoice.objects.create(question=question, label="No", order=2)
        self.client.force_login(self.staff)
        res = self.client.post(
            f"/brackets/api/streak-questions/{question.id}/resolve",
            data=json.dumps({"correct_choice_id": yes.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(question.correct_choice_id, yes.id)
        self.assertIsNotNone(question.resolved_at)


class StreakParticipantPicksApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.viewer = User.objects.create_user(username="viewer", password="x")
        self.other = User.objects.create_user(username="other", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.viewer,
            is_public=True,
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.viewer
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.other
        )

    def test_player_picks_only_include_resolved_questions(self):
        resolved = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Resolved Q",
            closes_at=timezone.now() - timezone.timedelta(hours=2),
            order=1,
        )
        yes = StreakQuestionChoice.objects.create(
            question=resolved, label="Yes", order=1
        )
        StreakQuestionChoice.objects.create(question=resolved, label="No", order=2)
        resolved.correct_choice = yes
        resolved.resolved_at = timezone.now()
        resolved.save(update_fields=["correct_choice", "resolved_at"])

        open_q = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Open Q",
            closes_at=timezone.now() + timezone.timedelta(days=1),
            order=2,
        )
        a = StreakQuestionChoice.objects.create(question=open_q, label="A", order=1)
        StreakQuestionChoice.objects.create(question=open_q, label="B", order=2)

        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=resolved,
            user=self.other,
            choice=yes,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=open_q,
            user=self.other,
            choice=a,
        )

        self.client.force_login(self.viewer)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/players/{self.other.id}/picks"
        )
        self.assertEqual(res.status_code, 200)
        picks = res.json()["picks"]
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["text"], "Resolved Q")


class StreakChallengeDeleteApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.creator = User.objects.create_user(username="host", password="x")
        self.joiner = User.objects.create_user(username="guest", password="x")
        self.competition = StreakCompetition.objects.create(name="Props")
        self.challenge = StreakChallenge.objects.create(
            name="Friends pool",
            streak_competition=self.competition,
            created_by=self.creator,
            is_public=False,
            join_code="STREAK01",
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.creator
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.joiner
        )

    def test_creator_can_delete_streak_challenge(self):
        self.client.force_login(self.creator)
        res = self.client.delete(
            f"/brackets/api/streak-challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            StreakChallenge.objects.filter(pk=self.challenge.pk).exists()
        )

    def test_non_creator_cannot_delete_streak_challenge(self):
        self.client.force_login(self.joiner)
        res = self.client.delete(
            f"/brackets/api/streak-challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 403)
        self.assertTrue(
            StreakChallenge.objects.filter(pk=self.challenge.pk).exists()
        )
