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

    def _seed_resolved_pick(
        self,
        *,
        user,
        closes_at,
        correct: bool,
        order: int,
    ) -> None:
        from brackets.utils.streak_scoring import resolve_question

        q = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text=f"Pick {order}",
            closes_at=closes_at,
            order=order,
        )
        right = StreakQuestionChoice.objects.create(question=q, label="Yes", order=0)
        wrong = StreakQuestionChoice.objects.create(question=q, label="No", order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q,
            user=user,
            choice=right if correct else wrong,
        )
        resolve_question(q, right.id)

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

    def test_projected_knockout_preview_uses_current_bonus_and_resets_consolation(self):
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
        self.challenge.knockout_transition_at = timezone.now() + timedelta(days=2)
        self.challenge.knockout_round_headstart = {"1": True}
        self.challenge.save(
            update_fields=["knockout_transition_at", "knockout_round_headstart"]
        )

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout"
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()["knockout"]
        first_match = payload["rounds"][0]["matches"][0]
        self.assertTrue(first_match["score_bonus_enabled"])
        self.assertEqual(first_match["score_a_correct"], 0)
        self.assertEqual(first_match["score_a_bonus"], 4)
        self.assertEqual(first_match["score_a"], 4)
        self.assertEqual(payload["consolation"][0]["display_name"], "Eve")
        self.assertEqual(payload["consolation"][0]["record"], "0-0")
        self.assertEqual(payload["consolation"][0]["win_pct"], 0)

    def test_streak_participant_picks_filters_by_scope(self):
        now = timezone.now()
        self.challenge.knockout_transition_at = now - timedelta(days=2)
        self.challenge.knockout_round_starts = {
            "2": (now - timedelta(hours=12)).isoformat()
        }
        self.challenge.save(
            update_fields=["knockout_transition_at", "knockout_round_starts"]
        )

        bob_p = StreakParticipant.objects.get(user=self.bob)
        bob_p.consolation_eligible_from = now - timedelta(hours=8)
        bob_p.save(update_fields=["consolation_eligible_from"])

        q_season = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Season Q",
            closes_at=now - timedelta(days=3),
            resolved_at=now - timedelta(days=3),
            order=0,
        )
        season_right = StreakQuestionChoice.objects.create(
            question=q_season, label="Yes", order=0
        )
        q_season.correct_choice = season_right
        q_season.save(update_fields=["correct_choice"])

        q_round = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Round 1 Q",
            closes_at=now - timedelta(days=1),
            resolved_at=now - timedelta(days=1),
            order=1,
        )
        round_right = StreakQuestionChoice.objects.create(
            question=q_round, label="Yes", order=0
        )
        q_round.correct_choice = round_right
        q_round.save(update_fields=["correct_choice"])

        q_consolation = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Consolation Q",
            closes_at=now - timedelta(hours=6),
            resolved_at=now - timedelta(hours=6),
            order=2,
        )
        consolation_right = StreakQuestionChoice.objects.create(
            question=q_consolation, label="Yes", order=0
        )
        q_consolation.correct_choice = consolation_right
        q_consolation.save(update_fields=["correct_choice"])

        for question, choice in [
            (q_season, season_right),
            (q_round, round_right),
            (q_consolation, consolation_right),
        ]:
            StreakPick.objects.create(
                streak_challenge=self.challenge,
                question=question,
                user=self.bob,
                choice=choice,
            )

        self.client.force_login(self.alice)
        base = f"/brackets/api/streak-challenges/{self.challenge.id}/players/{self.bob.id}/picks"
        streak_res = self.client.get(f"{base}?scope=streak")
        round_res = self.client.get(f"{base}?scope=round&round_index=1")
        consolation_res = self.client.get(f"{base}?scope=consolation")

        self.assertEqual(streak_res.status_code, 200)
        self.assertEqual(
            [row["text"] for row in streak_res.json()["picks"]],
            ["Season Q"],
        )
        self.assertEqual(round_res.status_code, 200)
        self.assertEqual(
            [row["text"] for row in round_res.json()["picks"]],
            ["Round 1 Q"],
        )
        self.assertEqual(consolation_res.status_code, 200)
        self.assertEqual(
            [row["text"] for row in consolation_res.json()["picks"]],
            ["Consolation Q"],
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
        self.assertEqual(header["value"], "Alice 4-2 Dave")

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
        from brackets.utils.streak_scoring import resolve_question

        base = timezone.now() - timedelta(days=5)
        for i in range(5):
            self._seed_resolved_pick(
                user=self.alice,
                closes_at=base + timedelta(hours=i),
                correct=True,
                order=i,
            )
        for i in range(2):
            self._seed_resolved_pick(
                user=self.alice,
                closes_at=base + timedelta(hours=10 + i),
                correct=False,
                order=10 + i,
            )

        self.client.force_login(self.host)
        res = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        alice_p = StreakParticipant.objects.get(user=self.alice)
        self.assertEqual(alice_p.frozen_wins, 5)
        self.assertEqual(alice_p.frozen_losses, 2)

        q = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Knockout pick",
            closes_at=timezone.now() + timedelta(hours=1),
            order=10,
        )
        right = StreakQuestionChoice.objects.create(question=q, label="Yes", order=0)
        StreakQuestionChoice.objects.create(question=q, label="No", order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q,
            user=self.alice,
            choice=right,
        )
        resolve_question(q, right.id)
        alice_p.refresh_from_db()

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/leaderboard"
        )
        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.json()["entries"] if r["user_id"] == self.alice.id)
        self.assertEqual(row["season_record"], "5-2")
        self.assertEqual(row["streak_record"], "5-2")
        self.assertEqual(row["knockout_record"], "1-0")
        self.assertEqual(row["consolation_record"], "0-0")
        self.assertEqual(row["total_record"], "6-2")
        self.assertEqual(row["total_win_pct"], 75)

    def test_knockout_leaderboard_recalculates_stale_total_record(self):
        from brackets.utils.streak_scoring import resolve_question

        base = timezone.now() - timedelta(days=5)
        for i in range(5):
            self._seed_resolved_pick(
                user=self.alice,
                closes_at=base + timedelta(hours=i),
                correct=True,
                order=i,
            )
        self._seed_resolved_pick(
            user=self.alice,
            closes_at=base + timedelta(hours=10),
            correct=False,
            order=10,
        )

        self.client.force_login(self.host)
        res = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        alice_p = StreakParticipant.objects.get(user=self.alice)
        self.assertEqual(alice_p.frozen_wins, 5)
        self.assertEqual(alice_p.frozen_losses, 1)

        q = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Knockout pick",
            closes_at=timezone.now() + timedelta(hours=1),
            order=10,
        )
        right = StreakQuestionChoice.objects.create(question=q, label="Yes", order=0)
        StreakQuestionChoice.objects.create(question=q, label="No", order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q,
            user=self.alice,
            choice=right,
        )
        resolve_question(q, right.id)

        alice_p.refresh_from_db()
        self.assertGreater(alice_p.wins, alice_p.frozen_wins)
        expected_record = f"{alice_p.wins}-{alice_p.losses}"

        # Simulate stats left stale by the old knockout recalc skip.
        alice_p.wins = alice_p.frozen_wins
        alice_p.losses = alice_p.frozen_losses
        alice_p.save(update_fields=["wins", "losses"])

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/leaderboard"
        )
        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.json()["entries"] if r["user_id"] == self.alice.id)
        self.assertEqual(row["season_record"], "5-1")
        self.assertEqual(row["total_record"], "6-1")
        self.assertEqual(row["total_win_pct"], 86)

    def test_knockout_total_record_counts_all_picks_at_deadline(self):
        from brackets.utils.streak_scoring import resolve_question

        base = timezone.now() - timedelta(days=5)
        for i in range(5):
            self._seed_resolved_pick(
                user=self.alice,
                closes_at=base + timedelta(hours=i),
                correct=True,
                order=i,
            )
        self._seed_resolved_pick(
            user=self.alice,
            closes_at=base + timedelta(hours=10),
            correct=False,
            order=10,
        )

        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )

        knockout_closes = timezone.now() + timedelta(hours=1)
        q1 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Knockout Q1",
            closes_at=knockout_closes,
            order=0,
        )
        q2 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Knockout Q2",
            closes_at=knockout_closes,
            order=1,
        )
        right1 = StreakQuestionChoice.objects.create(question=q1, label="Yes", order=0)
        StreakQuestionChoice.objects.create(question=q1, label="No", order=1)
        right2 = StreakQuestionChoice.objects.create(question=q2, label="Yes", order=0)
        StreakQuestionChoice.objects.create(question=q2, label="No", order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q1,
            user=self.alice,
            choice=right1,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q2,
            user=self.alice,
            choice=right2,
        )
        resolve_question(q1, right1.id)
        resolve_question(q2, right2.id)

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/leaderboard"
        )
        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.json()["entries"] if r["user_id"] == self.alice.id)
        self.assertEqual(row["season_record"], "5-1")
        self.assertEqual(row["total_record"], "7-1")

    def test_knockout_leaderboard_season_streak_unaffected_by_knockout_picks(self):
        from brackets.utils.streak_scoring import resolve_question

        base = timezone.now() - timedelta(days=5)
        for i in range(4):
            self._seed_resolved_pick(
                user=self.alice,
                closes_at=base + timedelta(hours=i),
                correct=True,
                order=i,
            )

        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )

        alice_p = StreakParticipant.objects.get(user=self.alice)
        self.assertEqual(alice_p.frozen_best_win_streak, 4)
        self.assertEqual(alice_p.frozen_streak_signed, 4)

        q = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Knockout pick",
            closes_at=timezone.now() + timedelta(hours=1),
            order=10,
        )
        wrong = StreakQuestionChoice.objects.create(question=q, label="Yes", order=0)
        right = StreakQuestionChoice.objects.create(question=q, label="No", order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q,
            user=self.alice,
            choice=wrong,
        )
        resolve_question(q, right.id)

        alice_p.refresh_from_db()
        self.assertEqual(alice_p.streak_signed, alice_p.frozen_streak_signed)
        self.assertEqual(alice_p.best_win_streak, alice_p.frozen_best_win_streak)
        self.assertGreater(alice_p.losses, alice_p.frozen_losses)

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/leaderboard"
        )
        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.json()["entries"] if r["user_id"] == self.alice.id)
        self.assertEqual(row["streak_signed"], 4)
        self.assertEqual(row["best_win_streak"], 4)
        self.assertEqual(row["current_display"], "4W")
        self.assertEqual(row["long_win_display"], "4W")

    def test_participant_picks_all_time_sections(self):
        from brackets.utils.streak_scoring import resolve_question

        base = timezone.now() - timedelta(days=5)
        self._seed_resolved_pick(
            user=self.alice,
            closes_at=base,
            correct=True,
            order=0,
        )

        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )

        knockout_q = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Bracket pick",
            closes_at=timezone.now() + timedelta(hours=1),
            order=1,
        )
        knockout_right = StreakQuestionChoice.objects.create(
            question=knockout_q, label="Yes", order=0
        )
        StreakQuestionChoice.objects.create(question=knockout_q, label="No", order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=knockout_q,
            user=self.alice,
            choice=knockout_right,
        )
        resolve_question(knockout_q, knockout_right.id)

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/players/{self.alice.id}/picks"
        )
        self.assertEqual(res.status_code, 200)
        picks = res.json()["picks"]
        self.assertEqual(len(picks), 2)
        self.assertEqual(picks[0]["section_label"], "Streak")
        self.assertEqual(picks[0]["section_key"], "streak")
        self.assertTrue(picks[1]["section_label"].startswith("Knockout: "))
        self.assertTrue(picks[1]["section_key"].startswith("knockout:"))

        res_consolation = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/players/{self.alice.id}/picks?scope=consolation"
        )
        self.assertEqual(res_consolation.status_code, 200)
        self.assertEqual(res_consolation.json()["picks"], [])

    def test_consolation_record_counts_all_picks_at_deadline(self):
        from brackets.utils.streak_knockout import recalculate_consolation_for_challenge
        from brackets.utils.streak_scoring import resolve_question

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
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        eve_p = StreakParticipant.objects.get(user=eve)
        eligible_from = eve_p.consolation_eligible_from
        self.assertIsNotNone(eligible_from)

        closes = eligible_from + timedelta(hours=1)
        q1 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Q1",
            closes_at=closes,
            order=0,
        )
        q2 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Q2",
            closes_at=closes,
            order=1,
        )
        wrong1 = StreakQuestionChoice.objects.create(question=q1, label="Yes", order=0)
        right1 = StreakQuestionChoice.objects.create(question=q1, label="No", order=1)
        wrong2 = StreakQuestionChoice.objects.create(question=q2, label="Yes", order=0)
        right2 = StreakQuestionChoice.objects.create(question=q2, label="No", order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q1,
            user=eve,
            choice=wrong1,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q2,
            user=eve,
            choice=wrong2,
        )
        resolve_question(q1, right1.id)
        resolve_question(q2, right2.id)

        eve_p = StreakParticipant.objects.get(user=eve)
        self.assertEqual(eve_p.consolation_wins, 0)
        self.assertEqual(eve_p.consolation_losses, 2)

        self.client.force_login(eve)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout"
        )
        self.assertEqual(res.status_code, 200)
        eve_row = next(
            row for row in res.json()["knockout"]["consolation"] if row["user_id"] == eve.id
        )
        self.assertEqual(eve_row["record"], "0-2")

        recalculate_consolation_for_challenge(self.challenge)
        eve_p.refresh_from_db()
        self.assertEqual(eve_p.consolation_losses, 2)

    def test_consolation_record_idempotent_on_re_resolve(self):
        from brackets.utils.streak_scoring import resolve_question

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
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        eve_p = StreakParticipant.objects.get(user=eve)
        eligible_from = eve_p.consolation_eligible_from
        self.assertIsNotNone(eligible_from)

        q1 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Q1",
            closes_at=eligible_from + timedelta(hours=1),
            order=0,
        )
        q2 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Q2",
            closes_at=eligible_from + timedelta(hours=2),
            order=0,
        )
        wrong = StreakQuestionChoice.objects.create(question=q1, label="Yes", order=0)
        right = StreakQuestionChoice.objects.create(question=q1, label="No", order=1)
        wrong2 = StreakQuestionChoice.objects.create(question=q2, label="Yes", order=0)
        right2 = StreakQuestionChoice.objects.create(question=q2, label="No", order=1)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q1,
            user=eve,
            choice=wrong,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=q2,
            user=eve,
            choice=wrong2,
        )
        resolve_question(q1, right.id)
        resolve_question(q2, right2.id)
        resolve_question(q1, right.id)
        resolve_question(q2, right2.id)

        eve_p = StreakParticipant.objects.get(user=eve)
        self.assertEqual(eve_p.consolation_wins, 0)
        self.assertEqual(eve_p.consolation_losses, 2)

        eve_p.consolation_losses = 4
        eve_p.save(update_fields=["consolation_losses"])

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout"
        )
        self.assertEqual(res.status_code, 200)
        eve_row = next(
            row for row in res.json()["knockout"]["consolation"] if row["user_id"] == eve.id
        )
        self.assertEqual(eve_row["record"], "0-2")

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

    def test_projected_knockout_includes_third_place_slot_when_enabled(self):
        self.challenge.knockout_third_place_match = True
        self.challenge.knockout_transition_at = timezone.now() + timedelta(days=2)
        self.challenge.save(
            update_fields=["knockout_third_place_match", "knockout_transition_at"]
        )

        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout"
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()["knockout"]
        self.assertTrue(payload["third_place_match_enabled"])
        self.assertIsNotNone(payload["third_place_match"])
        self.assertTrue(payload["third_place_match"]["is_third_place"])

    def test_semi_losers_join_third_place_not_consolation_when_enabled(self):
        from brackets.models import StreakKnockoutMatch

        self.challenge.knockout_third_place_match = True
        self.challenge.save(update_fields=["knockout_third_place_match"])

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
        for user in (self.alice, self.bob):
            StreakPick.objects.create(
                streak_challenge=self.challenge,
                question=q1,
                user=user,
                choice=right,
            )

        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/advance",
            data='{"headstart_enabled": true}',
            content_type="application/json",
        )
        res = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/advance",
            data='{"headstart_enabled": true}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        dave_p = StreakParticipant.objects.get(user=self.dave)
        carol_p = StreakParticipant.objects.get(user=self.carol)
        self.assertIsNone(dave_p.consolation_eligible_from)
        self.assertIsNone(carol_p.consolation_eligible_from)
        self.assertTrue(dave_p.in_knockout_bracket)
        self.assertTrue(carol_p.in_knockout_bracket)

        third_place = StreakKnockoutMatch.objects.get(
            knockout__streak_challenge=self.challenge,
            is_third_place=True,
        )
        self.assertEqual(third_place.player_a.user_id, self.dave.id)
        self.assertEqual(third_place.player_b.user_id, self.carol.id)

        payload = res.json()["knockout"]
        self.assertTrue(payload["third_place_match_enabled"])
        self.assertEqual(
            {payload["third_place_match"]["player_a"]["user_id"], payload["third_place_match"]["player_b"]["user_id"]},
            {self.dave.id, self.carol.id},
        )
        consolation_names = {row["display_name"] for row in payload["consolation"]}
        self.assertNotIn("Dave", consolation_names)
        self.assertNotIn("Carol", consolation_names)

    def test_consolation_rows_sort_by_record_win_pct_then_season_rank(self):
        from brackets.models import StreakKnockout
        from brackets.utils.streak_knockout import _consolation_rows

        self.client.force_login(self.host)
        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/start",
            data='{"confirm": "knockout"}',
            content_type="application/json",
        )
        knockout = StreakKnockout.objects.get(streak_challenge=self.challenge)
        now = timezone.now()

        bob_p = StreakParticipant.objects.get(user=self.bob)
        carol_p = StreakParticipant.objects.get(user=self.carol)
        dave_p = StreakParticipant.objects.get(user=self.dave)
        for participant in (bob_p, carol_p, dave_p):
            participant.consolation_eligible_from = now
            participant.in_knockout_bracket = False
            participant.save(
                update_fields=["consolation_eligible_from", "in_knockout_bracket"]
            )

        bob_p.consolation_wins = 3
        bob_p.consolation_losses = 0
        bob_p.save(update_fields=["consolation_wins", "consolation_losses"])
        carol_p.consolation_wins = 2
        carol_p.consolation_losses = 1
        carol_p.save(update_fields=["consolation_wins", "consolation_losses"])
        dave_p.consolation_wins = 2
        dave_p.consolation_losses = 1
        dave_p.save(update_fields=["consolation_wins", "consolation_losses"])

        rows = _consolation_rows(self.challenge, knockout)
        self.assertEqual(
            [row["display_name"] for row in rows],
            ["Bob", "Carol", "Dave"],
        )
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
        for user in (self.alice, self.bob):
            StreakPick.objects.create(
                streak_challenge=self.challenge,
                question=q1,
                user=user,
                choice=right,
            )

        self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/advance",
            data='{"headstart_enabled": true}',
            content_type="application/json",
        )
        res = self.client.post(
            f"/brackets/api/streak-challenges/{self.challenge.id}/knockout/advance",
            data='{"headstart_enabled": true}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        dave_p = StreakParticipant.objects.get(user=self.dave)
        carol_p = StreakParticipant.objects.get(user=self.carol)
        self.assertIsNotNone(dave_p.consolation_eligible_from)
        self.assertIsNotNone(carol_p.consolation_eligible_from)
        self.assertFalse(dave_p.in_knockout_bracket)
        self.assertFalse(carol_p.in_knockout_bracket)
        consolation_names = {
            row["display_name"] for row in res.json()["knockout"]["consolation"]
        }
        self.assertIn("Dave", consolation_names)
        self.assertIn("Carol", consolation_names)
