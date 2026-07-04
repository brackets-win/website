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
        eve = User.objects.create_user(username="eve", password="x")
        StreakParticipant.objects.create(
            streak_challenge=self.challenge,
            user=eve,
            display_name="Eve",
            wins=1,
            losses=5,
            best_win_streak=1,
            streak_signed=-1,
        )
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

        eve_p = StreakParticipant.objects.get(user=eve)
        self.assertFalse(eve_p.in_knockout_bracket)
        self.assertIsNotNone(eve_p.consolation_eligible_from)

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

    def test_knockout_get_endpoint_returns_projected_bracket_when_scheduled(self):
        self.challenge.knockout_transition_at = timezone.now() + timedelta(days=2)
        self.challenge.save(update_fields=["knockout_transition_at"])

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout"
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()["knockout"]
        self.assertTrue(payload["projected"])
        self.assertEqual(payload["status"], "SETUP")
        self.assertEqual(payload["total_rounds"], 2)
        self.assertEqual(payload["rounds"][0]["matches"][0]["player_a"]["display_name"], "Alice")
        self.assertEqual(payload["rounds"][0]["matches"][0]["player_b"]["display_name"], "Dave")
        self.assertEqual(payload["rounds"][1]["matches"][0]["player_a"], None)
        self.assertEqual(
            [row["display_name"] for row in payload["consolation"]],
            [],
        )

    def test_streak_detail_shows_knockout_matchup_header(self):
        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )

        self.client.force_login(self.alice)
        res = self.client.get(f"/brackets/api/streak-challenges/{self.challenge.id}")
        self.assertEqual(res.status_code, 200)
        header = res.json()["streak_challenge"]["knockout_header"]
        self.assertIsNotNone(header)
        self.assertEqual(header["kind"], "matchup")
        self.assertEqual(header["label"], "Semi Final")
        self.assertEqual(header["value"], "Alice 0-0 Dave")

    def test_streak_detail_shows_consolation_header(self):
        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        bob_p = StreakParticipant.objects.get(user=self.bob)
        dave_p = StreakParticipant.objects.get(user=self.dave)
        now = timezone.now()
        bob_p.in_knockout_bracket = False
        bob_p.consolation_eligible_from = now
        bob_p.consolation_wins = 5
        bob_p.consolation_losses = 2
        bob_p.save(
            update_fields=[
                "in_knockout_bracket",
                "consolation_eligible_from",
                "consolation_wins",
                "consolation_losses",
            ]
        )
        dave_p.in_knockout_bracket = False
        dave_p.consolation_eligible_from = now
        dave_p.consolation_wins = 4
        dave_p.consolation_losses = 3
        dave_p.save(
            update_fields=[
                "in_knockout_bracket",
                "consolation_eligible_from",
                "consolation_wins",
                "consolation_losses",
            ]
        )

        self.client.force_login(self.dave)
        res = self.client.get(f"/brackets/api/streak-challenges/{self.challenge.id}")
        self.assertEqual(res.status_code, 200)
        header = res.json()["streak_challenge"]["knockout_header"]
        self.assertIsNotNone(header)
        self.assertEqual(header["kind"], "consolation")
        self.assertEqual(header["label"], "CONSOLATION 2nd")
        self.assertEqual(header["value"], "4-3")

    def test_knockout_leaderboard_includes_season_and_total_fields(self):
        self.challenge.mode = StreakChallenge.Mode.KNOCKOUT
        self.challenge.save(update_fields=["mode"])
        alice_p = StreakParticipant.objects.get(user=self.alice)
        alice_p.frozen_wins = 5
        alice_p.frozen_losses = 2
        alice_p.wins = 7
        alice_p.losses = 3
        alice_p.save(
            update_fields=["frozen_wins", "frozen_losses", "wins", "losses"]
        )

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/leaderboard"
        )
        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.json()["entries"] if r["user_id"] == self.alice.id)
        self.assertEqual(row["season_record"], "5-2")
        self.assertEqual(row["season_win_pct"], 71)
        self.assertEqual(row["total_record"], "7-3")
        self.assertEqual(row["total_win_pct"], 70)

    def test_knockout_scores_include_correct_and_bonus_breakdown(self):
        now = timezone.now()
        self.challenge.knockout_transition_at = now - timedelta(days=2)
        self.challenge.knockout_round_starts = {
            "2": (now + timedelta(days=1)).isoformat()
        }
        self.challenge.knockout_round_headstart = {"1": True}
        self.challenge.save(
            update_fields=[
                "knockout_transition_at",
                "knockout_round_starts",
                "knockout_round_headstart",
            ]
        )

        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )

        q1 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Round 1 Q",
            closes_at=now - timedelta(days=1),
            resolved_at=now - timedelta(hours=1),
            order=0,
        )
        right = StreakQuestionChoice.objects.create(question=q1, label="Yes", order=0)
        StreakQuestionChoice.objects.create(question=q1, label="No", order=1)
        q1.correct_choice = right
        q1.save(update_fields=["correct_choice"])

        wrong = q1.choices.exclude(pk=right.pk).first()
        self.assertIsNotNone(wrong)

        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q1,
            user=self.alice,
            choice=right,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q1,
            user=self.dave,
            choice=wrong,
        )

        res = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/advance",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        rounds = res.json()["knockout"]["rounds"]
        first_match = rounds[0]["matches"][0]
        self.assertTrue(first_match["score_bonus_enabled"])
        self.assertEqual(first_match["score_a_correct"], 1)
        self.assertEqual(first_match["score_a_bonus"], 4)
        self.assertEqual(first_match["score_a"], 5)
        self.assertEqual(first_match["score_b_correct"], 0)
        self.assertEqual(first_match["score_b_bonus"], 2)
        self.assertEqual(first_match["score_b"], 2)
