"""Streak pick: one open pick per deadline, clear to switch."""

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


class StreakPickDeadlineTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="player", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.user,
            is_public=True,
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.user
        )
        self.closes = timezone.now() + timezone.timedelta(days=1)
        self.q1 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Q1",
            closes_at=self.closes,
            order=1,
        )
        self.c1a = StreakQuestionChoice.objects.create(
            question=self.q1, label="A", order=1
        )
        StreakQuestionChoice.objects.create(question=self.q1, label="B", order=2)
        self.q2 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Q2",
            closes_at=self.closes,
            order=2,
        )
        self.c2a = StreakQuestionChoice.objects.create(
            question=self.q2, label="A", order=1
        )
        StreakQuestionChoice.objects.create(question=self.q2, label="B", order=2)
        self.client.force_login(self.user)
        self.pick_url = "/brackets/api/streak-questions/{}/pick"
        self.body = {"streak_challenge_id": self.challenge.id}

    def test_second_pick_same_deadline_rejected(self):
        r1 = self.client.post(
            self.pick_url.format(self.q1.id),
            data=json.dumps({**self.body, "choice_id": self.c1a.id}),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(
            self.pick_url.format(self.q2.id),
            data=json.dumps({**self.body, "choice_id": self.c2a.id}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 409)

    def test_clear_pick_allows_switching_question(self):
        self.client.post(
            self.pick_url.format(self.q1.id),
            data=json.dumps({**self.body, "choice_id": self.c1a.id}),
            content_type="application/json",
        )
        clear = self.client.delete(
            self.pick_url.format(self.q1.id),
            data=json.dumps(self.body),
            content_type="application/json",
        )
        self.assertEqual(clear.status_code, 200)
        self.assertFalse(
            StreakPick.objects.filter(
                streak_challenge=self.challenge,
                question=self.q1,
                user=self.user,
            ).exists()
        )
        r2 = self.client.post(
            self.pick_url.format(self.q2.id),
            data=json.dumps({**self.body, "choice_id": self.c2a.id}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 200)

    def test_detail_marks_deadline_locked(self):
        self.client.post(
            self.pick_url.format(self.q1.id),
            data=json.dumps({**self.body, "choice_id": self.c1a.id}),
            content_type="application/json",
        )
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 200)
        by_id = {q["id"]: q for q in res.json()["questions"]}
        self.assertFalse(by_id[self.q1.id]["deadline_locked"])
        self.assertTrue(by_id[self.q1.id]["can_clear_pick"])
        self.assertTrue(by_id[self.q2.id]["deadline_locked"])
        self.assertEqual(by_id[self.q2.id]["locked_by_question_id"], self.q1.id)

    def test_past_closes_at_marks_question_closed(self):
        self.q1.closes_at = timezone.now() - timezone.timedelta(minutes=5)
        self.q1.save(update_fields=["closes_at"])
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 200)
        by_id = {q["id"]: q for q in res.json()["questions"]}
        self.assertFalse(by_id[self.q1.id]["is_open"])
        self.assertFalse(by_id[self.q1.id]["deadline_locked"])

    def test_pick_rejected_after_closes_at(self):
        self.q1.closes_at = timezone.now() - timezone.timedelta(minutes=5)
        self.q1.save(update_fields=["closes_at"])
        res = self.client.post(
            self.pick_url.format(self.q1.id),
            data=json.dumps({**self.body, "choice_id": self.c1a.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn(
            "closed",
            res.json()["error"]["message"].lower(),
        )
