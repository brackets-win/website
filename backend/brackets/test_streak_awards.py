"""Streak competition end state and challenge awards."""

import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakKnockout,
    StreakKnockoutMatch,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
    StreakQuestionChoice,
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

    def test_losing_streak_award(self):
        self.competition.ended_at = timezone.now()
        self.competition.save(update_fields=["ended_at"])
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/awards"
        )
        losers = res.json()["losing_streak"]["winners"]
        self.assertEqual(len(losers), 1)
        self.assertEqual(losers[0]["display_name"], "Alice")
        self.assertEqual(losers[0]["best_loss_streak"], 2)
        self.assertEqual(losers[0]["long_loss_display"], "2L")

    def test_losing_streak_allows_ties(self):
        charlie = User.objects.create_user(username="charlie", password="x")
        StreakParticipant.objects.create(
            streak_challenge=self.challenge,
            user=charlie,
            display_name="Charlie",
            wins=3,
            losses=5,
            streak_signed=-1,
            best_win_streak=2,
            best_loss_streak=2,
        )
        self.competition.ended_at = timezone.now()
        self.competition.save(update_fields=["ended_at"])
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/awards"
        )
        losers = res.json()["losing_streak"]["winners"]
        self.assertEqual(len(losers), 2)
        names = {row["display_name"] for row in losers}
        self.assertEqual(names, {"Alice", "Charlie"})

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


class StreakKnockoutAwardsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.host,
            is_public=True,
            mode=StreakChallenge.Mode.KNOCKOUT,
        )
        self.alice = User.objects.create_user(username="alice", password="x")
        self.bob = User.objects.create_user(username="bob", password="x")
        self.carol = User.objects.create_user(username="carol", password="x")
        self.dave = User.objects.create_user(username="dave", password="x")
        self.participants = {}
        for user, name, seed in [
            (self.alice, "Alice", 1),
            (self.bob, "Bob", 2),
            (self.carol, "Carol", 3),
            (self.dave, "Dave", 4),
        ]:
            self.participants[name] = StreakParticipant.objects.create(
                streak_challenge=self.challenge,
                user=user,
                display_name=name,
                wins=5,
                losses=1,
                best_win_streak=4,
                frozen_wins=5,
                frozen_losses=1,
                frozen_best_win_streak=4,
                frozen_streak_signed=1,
                knockout_seed=seed,
                in_knockout_bracket=True,
            )
        self.knockout = StreakKnockout.objects.create(
            streak_challenge=self.challenge,
            status=StreakKnockout.Status.COMPLETE,
            current_round=2,
            champion=self.participants["Bob"],
        )

    def _end_and_fetch(self) -> dict:
        self.competition.ended_at = timezone.now()
        self.competition.save(update_fields=["ended_at"])
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/awards"
        )
        self.assertEqual(res.status_code, 200)
        return res.json()

    def _finalize_match(
        self,
        *,
        round_index: int,
        position: int,
        player_a: StreakParticipant,
        player_b: StreakParticipant,
        winner: StreakParticipant,
        is_third_place: bool = False,
    ) -> StreakKnockoutMatch:
        return StreakKnockoutMatch.objects.create(
            knockout=self.knockout,
            round_index=round_index,
            position=position,
            player_a=player_a,
            player_b=player_b,
            seed_a=player_a.knockout_seed,
            seed_b=player_b.knockout_seed,
            winner=winner,
            finalized=True,
            is_third_place=is_third_place,
        )

    def test_podium_and_season_champion_with_third_place_match(self):
        alice = self.participants["Alice"]
        bob = self.participants["Bob"]
        carol = self.participants["Carol"]
        dave = self.participants["Dave"]
        # Semis: Alice beats Carol, Bob beats Dave
        self._finalize_match(
            round_index=1,
            position=1,
            player_a=alice,
            player_b=carol,
            winner=alice,
        )
        self._finalize_match(
            round_index=1,
            position=2,
            player_a=bob,
            player_b=dave,
            winner=bob,
        )
        # Final: Bob beats Alice
        self._finalize_match(
            round_index=2,
            position=1,
            player_a=alice,
            player_b=bob,
            winner=bob,
        )
        # Third place: Carol beats Dave
        self._finalize_match(
            round_index=2,
            position=2,
            player_a=carol,
            player_b=dave,
            winner=carol,
            is_third_place=True,
        )

        payload = self._end_and_fetch()
        self.assertTrue(payload["had_knockout"])
        self.assertEqual(
            [w["display_name"] for w in payload["knockout_first"]["winners"]],
            ["Bob"],
        )
        self.assertEqual(
            [w["display_name"] for w in payload["knockout_second"]["winners"]],
            ["Alice"],
        )
        self.assertEqual(
            [w["display_name"] for w in payload["knockout_third"]["winners"]],
            ["Carol"],
        )
        self.assertEqual(
            [w["display_name"] for w in payload["streak_champion"]["winners"]],
            ["Alice"],
        )

    def test_third_place_uses_both_semi_losers_alphabetically_without_match(self):
        alice = self.participants["Alice"]
        bob = self.participants["Bob"]
        carol = self.participants["Carol"]
        dave = self.participants["Dave"]
        self._finalize_match(
            round_index=1,
            position=1,
            player_a=alice,
            player_b=dave,
            winner=alice,
        )
        self._finalize_match(
            round_index=1,
            position=2,
            player_a=bob,
            player_b=carol,
            winner=bob,
        )
        self._finalize_match(
            round_index=2,
            position=1,
            player_a=alice,
            player_b=bob,
            winner=alice,
        )
        self.knockout.champion = alice
        self.knockout.save(update_fields=["champion"])

        payload = self._end_and_fetch()
        self.assertEqual(
            [w["display_name"] for w in payload["knockout_first"]["winners"]],
            ["Alice"],
        )
        self.assertEqual(
            [w["display_name"] for w in payload["knockout_second"]["winners"]],
            ["Bob"],
        )
        # Semi losers Carol + Dave, alphabetical
        self.assertEqual(
            [w["display_name"] for w in payload["knockout_third"]["winners"]],
            ["Carol", "Dave"],
        )


class StreakQuestionAwardsTests(TestCase):
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
        for user, name in [(self.alice, "Alice"), (self.bob, "Bob")]:
            StreakParticipant.objects.create(
                streak_challenge=self.challenge, user=user, display_name=name
            )
        self._next_close = timezone.now() - timedelta(days=10)

    def _make_question(self, text: str) -> StreakQuestion:
        self._next_close += timedelta(days=1)
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text=text,
            closes_at=self._next_close,
            resolved_at=timezone.now(),
        )
        right = StreakQuestionChoice.objects.create(
            question=question, label="Right", order=0
        )
        StreakQuestionChoice.objects.create(question=question, label="Wrong", order=1)
        question.correct_choice = right
        question.save(update_fields=["correct_choice"])
        return question

    def _pick(self, user, question: StreakQuestion, correct: bool) -> None:
        choice = question.correct_choice if correct else question.choices.get(
            label="Wrong"
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=question,
            user=user,
            choice=choice,
        )

    def _end_and_fetch(self) -> dict:
        self.competition.ended_at = timezone.now()
        self.competition.save(update_fields=["ended_at"])
        self.client.force_login(self.alice)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/awards"
        )
        self.assertEqual(res.status_code, 200)
        return res.json()

    def test_nicest_and_meanest_questions(self):
        nice = self._make_question("Nice one")
        mean = self._make_question("Mean one")
        # Nice: both correct. Mean: both wrong.
        self._pick(self.alice, nice, correct=True)
        self._pick(self.bob, nice, correct=True)
        self._pick(self.alice, mean, correct=False)
        self._pick(self.bob, mean, correct=False)

        payload = self._end_and_fetch()

        nicest = payload["nicest_question"]["winners"]
        self.assertEqual(len(nicest), 1)
        self.assertEqual(nicest[0]["question_id"], nice.id)
        self.assertEqual(nicest[0]["correct_count"], 2)

        meanest = payload["meanest_question"]["winners"]
        self.assertEqual(len(meanest), 1)
        self.assertEqual(meanest[0]["question_id"], mean.id)
        self.assertEqual(meanest[0]["incorrect_count"], 2)

    def test_question_awards_allow_ties(self):
        q1 = self._make_question("Q1")
        q2 = self._make_question("Q2")
        self._pick(self.alice, q1, correct=True)
        self._pick(self.alice, q2, correct=True)

        payload = self._end_and_fetch()
        nicest_ids = {w["question_id"] for w in payload["nicest_question"]["winners"]}
        self.assertEqual(nicest_ids, {q1.id, q2.id})

    def test_streak_ending_question(self):
        q1 = self._make_question("Q1")
        q2 = self._make_question("Q2")
        q3 = self._make_question("Q3")
        q4 = self._make_question("Q4")
        # Alice: 3W then break at q4 (broken streak = 3).
        self._pick(self.alice, q1, correct=True)
        self._pick(self.alice, q2, correct=True)
        self._pick(self.alice, q3, correct=True)
        self._pick(self.alice, q4, correct=False)
        # Bob: 1W then break at q2 (broken streak = 1).
        self._pick(self.bob, q1, correct=True)
        self._pick(self.bob, q2, correct=False)

        payload = self._end_and_fetch()
        winners = payload["streak_ending_question"]["winners"]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]["question_id"], q4.id)
        self.assertEqual(winners[0]["broken_win_streak"], 3)
        self.assertEqual(winners[0]["long_win_display"], "3W")
        self.assertEqual(winners[0]["player"]["display_name"], "Alice")
