"""H2H knockout mode for streak challenges."""

from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakKnockout,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
    StreakQuestionChoice,
    User,
)
from brackets.utils.streak_knockout import bracket_qualifier_count


class StreakKnockoutTests(TestCase):
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
        self.carol = User.objects.create_user(username="carol", password="x")
        self.dave = User.objects.create_user(username="dave", password="x")
        for user, name, wins, losses, best in [
            (self.alice, "Alice", 5, 1, 4),
            (self.bob, "Bob", 4, 2, 3),
            (self.carol, "Carol", 3, 3, 2),
            (self.dave, "Dave", 2, 4, 2),
        ]:
            StreakParticipant.objects.create(
                streak_challenge=self.challenge,
                user=user,
                display_name=name,
                wins=wins,
                losses=losses,
                best_win_streak=best,
                streak_signed=1,
            )

    def test_bracket_qualifier_count(self):
        self.assertEqual(bracket_qualifier_count(9), 8)
        self.assertEqual(bracket_qualifier_count(7), 4)
        self.assertEqual(bracket_qualifier_count(4), 4)

    def test_start_knockout_requires_confirm(self):
        self.client.force_login(self.host)
        res = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "nope"}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_start_knockout_freezes_stats_and_builds_bracket(self):
        self.client.force_login(self.host)
        res = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.mode, StreakChallenge.Mode.KNOCKOUT)
        knockout = StreakKnockout.objects.get(streak_challenge=self.challenge)
        self.assertEqual(knockout.status, StreakKnockout.Status.SETUP)
        self.assertEqual(knockout.matches.filter(round_index=1).count(), 2)

        alice = StreakParticipant.objects.get(user=self.alice)
        self.assertEqual(alice.frozen_best_win_streak, 4)
        self.assertTrue(alice.in_knockout_bracket)

        dave = StreakParticipant.objects.get(user=self.dave)
        self.assertFalse(dave.in_knockout_bracket)
        self.assertIsNotNone(dave.consolation_eligible_from)

    def test_advance_round_scores_and_eliminates(self):
        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        closes = timezone.now() - timedelta(days=5)
        q1 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Q1",
            closes_at=closes,
            resolved_at=timezone.now(),
            order=0,
        )
        right = StreakQuestionChoice.objects.create(question=q1, label="Yes", order=0)
        StreakQuestionChoice.objects.create(question=q1, label="No", order=1)
        q1.correct_choice = right
        q1.save(update_fields=["correct_choice"])

        alice_p = StreakParticipant.objects.get(user=self.alice)
        bob_p = StreakParticipant.objects.get(user=self.bob)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q1,
            user=self.alice,
            choice=right,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q1,
            user=self.bob,
            choice=right,
        )

        res = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/advance",
            data='{"headstart_enabled": true}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertFalse(payload["completed"])

        res2 = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/advance",
            data='{"headstart_enabled": true}',
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 200)
        knockout = StreakKnockout.objects.get(streak_challenge=self.challenge)
        self.assertEqual(knockout.status, StreakKnockout.Status.IN_PROGRESS)
        self.assertEqual(knockout.current_round, 2)

        alice_p.refresh_from_db()
        bob_p.refresh_from_db()
        self.assertTrue(
            alice_p.in_knockout_bracket or bob_p.in_knockout_bracket
        )

    def test_knockout_get_endpoint(self):
        self.client.force_login(self.alice)
        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("rounds", res.json()["knockout"])
