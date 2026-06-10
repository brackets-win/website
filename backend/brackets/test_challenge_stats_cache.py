"""Cached challenge stats invalidate when entries change."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketChallenge, BracketContestant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.challenge_stats import (
    CHALLENGE_STATS_CACHE_KEY,
    CHALLENGE_STATS_REVISION_KEY,
    bump_challenge_stats_revision,
    compute_challenge_stats,
    get_challenge_stats,
    get_challenge_stats_revision,
    invalidate_challenge_stats_for_user_bracket,
)
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell

User = get_user_model()


class ChallengeStatsCacheTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.u1 = User.objects.create_user(username="u1", password="x")
        self.u2 = User.objects.create_user(username="u2", password="x")
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "stats-cache", "Stats Cache", 8, self.host
        )
        self.teams = [
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(8)
        ]
        self.challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=self.bracket,
            created_by=self.host,
        )

    def _submit(self, user, gp: dict) -> UserBracket:
        ub = UserBracket.objects.create(
            bracket=self.bracket,
            user=user,
            challenge=self.challenge,
            is_master=False,
            metadata={"group_positions": gp},
        )
        ub.submitted_at = timezone.now()
        ub.save(update_fields=["submitted_at", "metadata"])
        ensure_knockout_matchup_shell(ub)
        return ub

    def test_stats_are_cached_on_first_read(self):
        self._submit(
            self.u1,
            {
                "A": {
                    "1": self.teams[0].id,
                    "2": self.teams[1].id,
                    "3": self.teams[2].id,
                    "4": self.teams[3].id,
                },
                "B": {
                    "1": self.teams[4].id,
                    "2": self.teams[5].id,
                    "3": self.teams[6].id,
                    "4": self.teams[7].id,
                },
            },
        )
        get_challenge_stats(self.challenge)
        self.challenge.refresh_from_db()
        cache = self.challenge.metadata.get(CHALLENGE_STATS_CACHE_KEY)
        self.assertIsInstance(cache, dict)
        self.assertEqual(
            cache["revision"], get_challenge_stats_revision(self.challenge)
        )
        self.assertEqual(cache["submitted_count"], 1)

    def test_bump_invalidates_cached_stats(self):
        self._submit(
            self.u1,
            {
                "A": {
                    "1": self.teams[0].id,
                    "2": self.teams[1].id,
                    "3": self.teams[2].id,
                    "4": self.teams[3].id,
                },
                "B": {
                    "1": self.teams[4].id,
                    "2": self.teams[5].id,
                    "3": self.teams[6].id,
                    "4": self.teams[7].id,
                },
            },
        )
        get_challenge_stats(self.challenge)
        old_revision = get_challenge_stats_revision(self.challenge)
        bump_challenge_stats_revision(self.challenge)
        self.challenge.refresh_from_db()
        stale = self.challenge.metadata.get(CHALLENGE_STATS_CACHE_KEY)
        self.assertIsNone(stale)
        stats = get_challenge_stats(self.challenge)
        self.challenge.refresh_from_db()
        cache = self.challenge.metadata.get(CHALLENGE_STATS_CACHE_KEY)
        self.assertEqual(cache["revision"], get_challenge_stats_revision(self.challenge))
        self.assertGreater(get_challenge_stats_revision(self.challenge), old_revision)
        self.assertEqual(stats["submitted_count"], 1)

    def test_new_submission_recomputes_stats(self):
        gp = {
            "A": {
                "1": self.teams[0].id,
                "2": self.teams[1].id,
                "3": self.teams[2].id,
                "4": self.teams[3].id,
            },
            "B": {
                "1": self.teams[4].id,
                "2": self.teams[5].id,
                "3": self.teams[6].id,
                "4": self.teams[7].id,
            },
        }
        self._submit(self.u1, gp)
        stats_one = get_challenge_stats(self.challenge)
        self.assertEqual(stats_one["submitted_count"], 1)

        ub2 = self._submit(self.u2, gp)
        invalidate_challenge_stats_for_user_bracket(ub2)
        stats_two = get_challenge_stats(self.challenge)
        self.assertEqual(stats_two["submitted_count"], 2)

    def test_compute_still_available_for_tests(self):
        self.assertEqual(
            compute_challenge_stats(self.challenge)["submitted_count"],
            0,
        )
        self.challenge.refresh_from_db()
        self.assertIsNone(self.challenge.metadata.get(CHALLENGE_STATS_REVISION_KEY))
