"""Cached streak challenge stats invalidate when questions close."""

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
from brackets.utils.streak_challenge_stats import (
    STREAK_STATS_CACHE_KEY,
    STREAK_STATS_REVISION_KEY,
    bump_streak_stats_revision,
    compute_streak_challenge_stats,
    get_streak_challenge_stats,
    get_streak_stats_revision,
)
from brackets.utils.streak_scoring import resolve_question

User = get_user_model()


class StreakChallengeStatsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="player", password="x")
        self.other = User.objects.create_user(username="other", password="x")
        self.third = User.objects.create_user(username="zebra", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.user,
            is_public=True,
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.user, display_name="Alpha"
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.other, display_name="Beta"
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.third, display_name="Zebra"
        )

    def _make_resolved_question(self, *, text="Winner?"):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text=text,
            closes_at=timezone.now() - timezone.timedelta(hours=1),
            order=1,
        )
        yes = StreakQuestionChoice.objects.create(
            question=question, label="Yes", order=1
        )
        no = StreakQuestionChoice.objects.create(question=question, label="No", order=2)
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=question,
            user=self.user,
            choice=yes,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=question,
            user=self.other,
            choice=no,
        )
        resolve_question(question, yes.id)
        question.refresh_from_db()
        return question, yes, no

    def test_stats_include_pickers_sorted_by_display_name(self):
        question, yes, _no = self._make_resolved_question()
        stats = compute_streak_challenge_stats(self.challenge)
        row = next(q for q in stats["questions"] if q["question_id"] == question.id)
        yes_choice = next(c for c in row["choices"] if c["id"] == yes.id)
        self.assertEqual(yes_choice["pick_count"], 1)
        self.assertEqual(yes_choice["pick_pct"], 50)
        self.assertEqual(
            yes_choice["pickers"],
            [{"user_id": self.user.id, "display_name": "Alpha"}],
        )
        no_choice = next(c for c in row["choices"] if c["label"] == "No")
        self.assertEqual(
            no_choice["pickers"],
            [{"user_id": self.other.id, "display_name": "Beta"}],
        )

    def test_stats_are_cached_on_first_read(self):
        self._make_resolved_question()
        get_streak_challenge_stats(self.challenge)
        self.challenge.refresh_from_db()
        cache = self.challenge.metadata.get(STREAK_STATS_CACHE_KEY)
        self.assertIsInstance(cache, dict)
        self.assertEqual(
            cache["revision"], get_streak_stats_revision(self.challenge)
        )
        self.assertEqual(len(cache["questions"]), 1)

    def test_resolve_bumps_stats_revision(self):
        question, yes, _no = self._make_resolved_question(text="Q1")
        self.challenge.refresh_from_db()
        revision_after_first = get_streak_stats_revision(self.challenge)
        get_streak_challenge_stats(self.challenge)

        question2 = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Q2",
            closes_at=timezone.now() - timezone.timedelta(minutes=30),
            order=2,
        )
        choice = StreakQuestionChoice.objects.create(
            question=question2, label="A", order=1
        )
        StreakQuestionChoice.objects.create(question=question2, label="B", order=2)
        resolve_question(question2, choice.id)

        self.challenge.refresh_from_db()
        self.assertGreater(
            get_streak_stats_revision(self.challenge), revision_after_first
        )
        stale = self.challenge.metadata.get(STREAK_STATS_CACHE_KEY)
        self.assertIsNone(stale)
        stats = get_streak_challenge_stats(self.challenge)
        self.assertEqual(len(stats["questions"]), 2)

    def test_stats_api_requires_participant(self):
        self._make_resolved_question()
        outsider = User.objects.create_user(username="outsider", password="x")
        self.client.force_login(outsider)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/stats"
        )
        self.assertEqual(res.status_code, 403)

    def test_stats_api_returns_payload(self):
        question, yes, _no = self._make_resolved_question()
        self.client.force_login(self.user)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/stats"
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        row = next(q for q in payload["questions"] if q["question_id"] == question.id)
        yes_choice = next(c for c in row["choices"] if c["id"] == yes.id)
        self.assertEqual(yes_choice["pick_count"], 1)
        self.assertIn("pickers", yes_choice)

    def test_bump_invalidates_cached_stats(self):
        self._make_resolved_question()
        get_streak_challenge_stats(self.challenge)
        old_revision = get_streak_stats_revision(self.challenge)
        bump_streak_stats_revision(self.challenge)
        self.challenge.refresh_from_db()
        self.assertIsNone(self.challenge.metadata.get(STREAK_STATS_CACHE_KEY))
        stats = get_streak_challenge_stats(self.challenge)
        self.assertEqual(len(stats["questions"]), 1)
        self.assertGreater(get_streak_stats_revision(self.challenge), old_revision)
