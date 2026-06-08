"""Cached leaderboard scores invalidate when the master bracket changes."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketChallenge, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.leaderboard_scoring import (
    LEADERBOARD_SCORES_KEY,
    bump_master_scoring_revision,
    get_leaderboard_scores,
    get_master_scoring_revision,
    load_leaderboard_scoring_context,
    refresh_user_bracket_leaderboard_cache,
)

User = get_user_model()


class LeaderboardScoringCacheTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.player = User.objects.create_user(username="player", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "cache-test", "Cache", 4, self.host
        )
        self.challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=self.bracket,
            created_by=self.host,
        )
        self.ub = UserBracket.objects.create(
            user=self.player,
            bracket=self.bracket,
            challenge=self.challenge,
            submitted_at=timezone.now(),
        )

    def test_scores_are_cached_on_first_read(self):
        ctx = load_leaderboard_scoring_context(self.bracket)
        get_leaderboard_scores(self.ub, ctx)
        self.ub.refresh_from_db()
        cache = self.ub.metadata.get(LEADERBOARD_SCORES_KEY)
        self.assertIsInstance(cache, dict)
        self.assertEqual(cache["revision"], get_master_scoring_revision(self.bracket))

    def test_master_bump_invalidates_cached_scores(self):
        ctx = load_leaderboard_scoring_context(self.bracket)
        get_leaderboard_scores(self.ub, ctx)
        old_revision = get_master_scoring_revision(self.bracket)
        bump_master_scoring_revision(self.bracket)
        self.ub.refresh_from_db()
        cache = self.ub.metadata.get(LEADERBOARD_SCORES_KEY)
        self.assertEqual(cache["revision"], old_revision)
        bundle = get_leaderboard_scores(
            self.ub, ctx, revision=get_master_scoring_revision(self.bracket)
        )
        self.ub.refresh_from_db()
        new_cache = self.ub.metadata.get(LEADERBOARD_SCORES_KEY)
        self.assertEqual(new_cache["revision"], get_master_scoring_revision(self.bracket))
        self.assertIsNotNone(bundle.score)

    def test_refresh_updates_cache_after_user_pick_change(self):
        ctx = load_leaderboard_scoring_context(self.bracket)
        get_leaderboard_scores(self.ub, ctx)
        refresh_user_bracket_leaderboard_cache(self.ub)
        self.ub.refresh_from_db()
        cache = self.ub.metadata.get(LEADERBOARD_SCORES_KEY)
        self.assertEqual(cache["revision"], get_master_scoring_revision(self.bracket))
