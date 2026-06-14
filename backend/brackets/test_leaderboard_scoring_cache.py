"""Cached leaderboard scores invalidate when the master bracket changes."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketChallenge, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.leaderboard_scoring import (
    LEADERBOARD_SCORES_KEY,
    count_stale_submitted_leaderboard_scores,
    get_master_scoring_revision,
    is_master_scoring_pending,
    load_leaderboard_scoring_context,
    mark_master_scoring_pending,
    materialize_leaderboard_scores_batch,
    materialize_leaderboard_scores_for_bracket,
    on_master_bracket_changed,
    read_stored_leaderboard_scores,
    refresh_all_submitted_leaderboard_scores_for_bracket,
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

    def test_refresh_writes_materialized_columns(self):
        refresh_user_bracket_leaderboard_cache(self.ub)
        self.ub.refresh_from_db()
        self.assertIsNotNone(self.ub.leaderboard_score)
        self.assertEqual(
            self.ub.leaderboard_scores_revision,
            get_master_scoring_revision(self.bracket),
        )
        cache = self.ub.metadata.get(LEADERBOARD_SCORES_KEY)
        self.assertIsInstance(cache, dict)
        self.assertEqual(cache["revision"], get_master_scoring_revision(self.bracket))

    def test_read_does_not_compute_on_miss(self):
        bundle = read_stored_leaderboard_scores(self.ub)
        self.assertIsNone(bundle.score)
        self.ub.refresh_from_db()
        self.assertIsNone(self.ub.leaderboard_score)

    def test_master_change_recomputes_all_submitted(self):
        refresh_user_bracket_leaderboard_cache(self.ub)
        old_revision = get_master_scoring_revision(self.bracket)
        on_master_bracket_changed(self.bracket)
        self.ub.refresh_from_db()
        self.assertEqual(
            self.ub.leaderboard_scores_revision,
            get_master_scoring_revision(self.bracket),
        )
        self.assertNotEqual(
            get_master_scoring_revision(self.bracket),
            old_revision,
        )
        bundle = read_stored_leaderboard_scores(self.ub)
        self.assertIsNotNone(bundle.score)

    def test_refresh_all_submitted_for_bracket(self):
        count = refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)
        self.assertEqual(count, 1)
        self.ub.refresh_from_db()
        self.assertIsNotNone(self.ub.leaderboard_score)

    def test_read_returns_stored_after_refresh(self):
        ctx = load_leaderboard_scoring_context(self.bracket)
        del ctx
        refresh_user_bracket_leaderboard_cache(self.ub)
        bundle = read_stored_leaderboard_scores(self.ub)
        self.assertIsNotNone(bundle.score)

    def test_deferred_master_change_leaves_scores_stale_until_materialized(self):
        refresh_user_bracket_leaderboard_cache(self.ub)
        old_revision = self.ub.leaderboard_scores_revision
        mark_master_scoring_pending(self.bracket)
        self.ub.refresh_from_db()
        self.assertTrue(is_master_scoring_pending(self.bracket))
        self.assertEqual(self.ub.leaderboard_scores_revision, old_revision)
        materialize_leaderboard_scores_for_bracket(self.bracket)
        self.ub.refresh_from_db()
        self.assertFalse(is_master_scoring_pending(self.bracket))
        self.assertEqual(
            self.ub.leaderboard_scores_revision,
            get_master_scoring_revision(self.bracket),
        )

    def test_on_master_changed_without_materialize_defers_recompute(self):
        refresh_user_bracket_leaderboard_cache(self.ub)
        stored_revision = self.ub.leaderboard_scores_revision
        on_master_bracket_changed(self.bracket, materialize=False)
        self.ub.refresh_from_db()
        self.assertTrue(is_master_scoring_pending(self.bracket))
        self.assertEqual(self.ub.leaderboard_scores_revision, stored_revision)

    def test_materialize_batch_updates_stale_entries_only(self):
        refresh_user_bracket_leaderboard_cache(self.ub)
        player_b = User.objects.create_user(username="player_b", password="x")
        ub_b = UserBracket.objects.create(
            user=player_b,
            bracket=self.bracket,
            challenge=self.challenge,
            submitted_at=timezone.now(),
        )
        refresh_user_bracket_leaderboard_cache(ub_b)
        mark_master_scoring_pending(self.bracket)
        self.assertEqual(count_stale_submitted_leaderboard_scores(self.bracket), 2)

        result = materialize_leaderboard_scores_batch(self.bracket, limit=1)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["remaining_count"], 1)
        self.assertTrue(result["leaderboard_scores_pending"])

        result = materialize_leaderboard_scores_batch(self.bracket, limit=1)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["remaining_count"], 0)
        self.assertFalse(result["leaderboard_scores_pending"])
        revision = get_master_scoring_revision(self.bracket)
        self.ub.refresh_from_db()
        ub_b.refresh_from_db()
        self.assertEqual(self.ub.leaderboard_scores_revision, revision)
        self.assertEqual(ub_b.leaderboard_scores_revision, revision)
