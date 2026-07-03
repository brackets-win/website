"""Scheduled knockout transition and per-question knockout rules."""

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


class StreakKnockoutScheduleTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="x")
        self.player = User.objects.create_user(username="player", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.host,
            is_public=True,
        )
        for user in (self.host, self.player):
            StreakParticipant.objects.create(streak_challenge=self.challenge, user=user)

        now = timezone.now()
        self.streak_closes = now + timezone.timedelta(days=1)
        self.knockout_closes = now + timezone.timedelta(days=3)
        self.transition_at = now + timezone.timedelta(days=2)

        self.q_streak = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Streak Q",
            closes_at=self.streak_closes,
            order=1,
        )
        self.c_streak = StreakQuestionChoice.objects.create(
            question=self.q_streak, label="A", order=1
        )
        StreakQuestionChoice.objects.create(question=self.q_streak, label="B", order=2)

        self.q_knockout = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Knockout Q",
            closes_at=self.knockout_closes,
            order=2,
        )
        self.c_knockout = StreakQuestionChoice.objects.create(
            question=self.q_knockout, label="A", order=1
        )
        StreakQuestionChoice.objects.create(question=self.q_knockout, label="B", order=2)

        self.q_knockout_only = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Knockout Only Q",
            closes_at=self.knockout_closes,
            order=3,
            knockout_only=True,
        )
        StreakQuestionChoice.objects.create(
            question=self.q_knockout_only, label="A", order=1
        )
        StreakQuestionChoice.objects.create(
            question=self.q_knockout_only, label="B", order=2
        )

        self.challenge.knockout_transition_at = self.transition_at
        self.challenge.save(update_fields=["knockout_transition_at"])

        self.client.force_login(self.player)
        self.pick_url = "/brackets/api/streak-questions/{}/pick"
        self.body = {"streak_challenge_id": self.challenge.id}

    def test_knockout_only_hidden_without_schedule(self):
        self.challenge.knockout_transition_at = None
        self.challenge.save(update_fields=["knockout_transition_at"])
        res = self.client.get(f"/brackets/api/streak-challenges/{self.challenge.id}")
        ids = {q["id"] for q in res.json()["questions"]}
        self.assertIn(self.q_streak.id, ids)
        self.assertIn(self.q_knockout.id, ids)
        self.assertNotIn(self.q_knockout_only.id, ids)

    def test_knockout_only_visible_when_scheduled(self):
        res = self.client.get(f"/brackets/api/streak-challenges/{self.challenge.id}")
        ids = {q["id"] for q in res.json()["questions"]}
        self.assertIn(self.q_knockout_only.id, ids)

    def test_same_deadline_streak_and_knockout_picks_allowed(self):
        same = timezone.now() + timezone.timedelta(days=4)
        self.transition_at = timezone.now() + timezone.timedelta(days=2)
        self.challenge.knockout_transition_at = self.transition_at
        self.challenge.save(update_fields=["knockout_transition_at"])
        self.q_streak.closes_at = same
        self.q_streak.save(update_fields=["closes_at"])
        self.q_knockout.closes_at = same
        self.q_knockout.save(update_fields=["closes_at"])

        r1 = self.client.post(
            self.pick_url.format(self.q_streak.id),
            data=json.dumps({**self.body, "choice_id": self.c_streak.id}),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(
            self.pick_url.format(self.q_knockout.id),
            data=json.dumps({**self.body, "choice_id": self.c_knockout.id}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 200)

    def test_knockout_phase_labels_on_questions(self):
        res = self.client.get(f"/brackets/api/streak-challenges/{self.challenge.id}")
        by_id = {q["id"]: q for q in res.json()["questions"]}
        self.assertFalse(by_id[self.q_streak.id]["is_knockout_pick"])
        self.assertIsNone(by_id[self.q_streak.id]["knockout_phase_label"])
        self.assertTrue(by_id[self.q_knockout.id]["is_knockout_pick"])
        self.assertEqual(by_id[self.q_knockout.id]["knockout_phase_label"], "Final")

    def test_schedule_endpoint_requires_round_times_for_larger_bracket(self):
        eve = User.objects.create_user(username="eve", password="x")
        frank = User.objects.create_user(username="frank", password="x")
        for user in (eve, frank):
            StreakParticipant.objects.create(streak_challenge=self.challenge, user=user)
        self.client.force_login(self.host)
        transition = (timezone.now() + timezone.timedelta(days=5)).isoformat()
        res = self.client.patch(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/schedule",
            data=json.dumps(
                {
                    "knockout_transition_at": transition,
                    "knockout_round_starts": {},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_schedule_endpoint_saves_two_player_final_only(self):
        self.client.force_login(self.host)
        transition = (timezone.now() + timezone.timedelta(days=5)).isoformat()
        res = self.client.patch(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/schedule",
            data=json.dumps(
                {
                    "knockout_transition_at": transition,
                    "knockout_round_starts": {},
                }
            ),
            content_type="application/json",
        )
        # Two participants -> one knockout round (Final), no extra round times needed.
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["knockout_phases"]), 1)
        self.assertEqual(data["knockout_phases"][0]["label"], "Final")

    def test_auto_start_knockout_when_transition_passed(self):
        self.challenge.knockout_transition_at = timezone.now() - timezone.timedelta(
            minutes=1
        )
        self.challenge.save(update_fields=["knockout_transition_at"])
        res = self.client.get(f"/brackets/api/streak-challenges/{self.challenge.id}")
        self.assertEqual(res.status_code, 200)
        self.challenge.refresh_from_db()
        self.assertTrue(self.challenge.is_knockout)
        from brackets.models import StreakKnockout

        knockout = StreakKnockout.objects.get(streak_challenge=self.challenge)
        self.assertEqual(knockout.status, StreakKnockout.Status.SETUP)
