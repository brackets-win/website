"""Streak competition end state and challenge awards."""

import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakParticipant,
    User,
)


class StreakAwardsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.host,
            is_public=True,
        )
        self.alice = User.objects.create_user(username="alice", password="x")
        self.bob = User.objects.create_user(username="bob", password="x")
        StreakParticipant.objects.create(
            streak_challenge=self.challenge,
            user=self.host,
            display_name="Host",
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge,
            user=self.alice,
            display_name="Alice",
            wins=8,
            losses=2,
            streak_signed=3,
            best_win_streak=5,
            best_loss_streak=2,
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge,
            user=self.bob,
            display_name="Bob",
            wins=8,
            losses=2,
            streak_signed=1,
            best_win_streak=4,
            best_loss_streak=1,
        )

    def test_awards_blocked_until_competition_ended(self):
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/awards"
        )
        self.assertEqual(res.status_code, 400)

    def test_streak_champion_uses_long_win_tiebreakers(self):
        self.competition.ended_at = timezone.now()
        self.competition.save(update_fields=["ended_at"])
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/awards"
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        champions = payload["streak_champion"]["winners"]
        self.assertEqual(len(champions), 1)
        self.assertEqual(champions[0]["display_name"], "Alice")
        self.assertEqual(champions[0]["best_win_streak"], 5)

    def test_streak_champion_includes_rank_one_ties(self):
        charlie = User.objects.create_user(username="charlie", password="x")
        StreakParticipant.objects.create(
            streak_challenge=self.challenge,
            user=charlie,
            display_name="Charlie",
            wins=8,
            losses=2,
            streak_signed=3,
            best_win_streak=5,
            best_loss_streak=2,
        )
        self.competition.ended_at = timezone.now()
        self.competition.save(update_fields=["ended_at"])
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/awards"
        )
        champions = res.json()["streak_champion"]["winners"]
        self.assertEqual(len(champions), 2)
        names = {row["display_name"] for row in champions}
        self.assertEqual(names, {"Alice", "Charlie"})

    def test_best_picker_allows_ties(self):
        self.competition.ended_at = timezone.now()
        self.competition.save(update_fields=["ended_at"])
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/awards"
        )
        pickers = res.json()["best_picker"]["winners"]
        self.assertEqual(len(pickers), 2)
        names = {row["display_name"] for row in pickers}
        self.assertEqual(names, {"Alice", "Bob"})

    def test_admin_can_end_competition(self):
        self.host.is_staff = True
        self.host.save(update_fields=["is_staff"])
        self.client.force_login(self.host)
        res = self.client.patch(
            f"/brackets/api/streak-competitions/{self.competition.id}",
            data=json.dumps({"end_competition": True}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.competition.refresh_from_db()
        self.assertIsNotNone(self.competition.ended_at)

    def test_summary_includes_competition_is_over(self):
        self.competition.ended_at = timezone.now() - timedelta(hours=1)
        self.competition.save(update_fields=["ended_at"])
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}"
        )
        self.assertTrue(res.json()["streak_challenge"]["competition_is_over"])
