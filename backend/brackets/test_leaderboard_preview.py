"""Leaderboard preview for home page tiles."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import (
    BracketChallenge,
    StreakChallenge,
    StreakCompetition,
    StreakParticipant,
    UserBracket,
)
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.leaderboard_preview import (
    bracket_challenge_leaderboard_preview,
    streak_challenge_leaderboard_preview,
)

User = get_user_model()


class LeaderboardPreviewTests(TestCase):
    def test_bracket_challenge_preview_top_by_score(self):
        host = User.objects.create_user(username="host", password="x")
        u1 = User.objects.create_user(username="alice", password="x")
        u2 = User.objects.create_user(username="bob", password="x")
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "lb-prev", "LB", 4, host
        )
        challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=bracket,
            created_by=host,
        )
        self.assertIsNotNone(bracket.get_master_bracket())

        ub_alice = UserBracket.objects.create(
            user=u1,
            bracket=bracket,
            challenge=challenge,
            display_name="Alice",
        )
        ub_bob = UserBracket.objects.create(
            user=u2,
            bracket=bracket,
            challenge=challenge,
            display_name="Bob",
        )
        ub_alice.submitted_at = timezone.now()
        ub_alice.save(update_fields=["submitted_at"])
        ub_bob.submitted_at = timezone.now()
        ub_bob.save(update_fields=["submitted_at"])

        preview = bracket_challenge_leaderboard_preview(challenge, u1)
        self.assertEqual(len(preview["top"]), 2)
        self.assertEqual(preview["top"][0]["display_name"], "Alice")
        self.assertTrue(preview["top"][0]["is_viewer"])
        self.assertIsNone(preview["viewer"])
        self.assertFalse(preview["gap_before_viewer"])

    def test_streak_preview_sorted_by_streak(self):
        host = User.objects.create_user(username="host", password="x")
        u1 = User.objects.create_user(username="p1", password="x")
        u2 = User.objects.create_user(username="p2", password="x")
        competition = StreakCompetition.objects.create(name="Streak comp")
        challenge = StreakChallenge.objects.create(
            name="Streak",
            streak_competition=competition,
            created_by=host,
            is_public=True,
        )
        StreakParticipant.objects.create(
            streak_challenge=challenge, user=u1, wins=3, losses=1, streak_signed=2
        )
        StreakParticipant.objects.create(
            streak_challenge=challenge, user=u2, wins=1, losses=2, streak_signed=-1
        )
        preview = streak_challenge_leaderboard_preview(challenge, u1)
        self.assertEqual(preview["top"][0]["display_name"], "p1")
        self.assertEqual(preview["top"][0]["points_label"], "2W")
        self.assertTrue(preview["top"][0]["is_viewer"])
        self.assertIsNone(preview["viewer"])

    def test_viewer_below_top_three_with_gap(self):
        host = User.objects.create_user(username="host", password="x")
        viewer = User.objects.create_user(username="viewer", password="x")
        competition = StreakCompetition.objects.create(name="Big comp")
        challenge = StreakChallenge.objects.create(
            name="Big",
            streak_competition=competition,
            created_by=host,
            is_public=True,
        )
        for i, streak in enumerate([5, 4, 3, 2, 1]):
            u = viewer if streak == 1 else User.objects.create_user(
                username=f"u{i}", password="x"
            )
            StreakParticipant.objects.create(
                streak_challenge=challenge,
                user=u,
                wins=max(streak, 0),
                losses=0,
                streak_signed=streak,
            )

        preview = streak_challenge_leaderboard_preview(challenge, viewer, limit=3)
        self.assertEqual(len(preview["top"]), 3)
        self.assertIsNotNone(preview["viewer"])
        self.assertEqual(preview["viewer"]["display_name"], "viewer")
        self.assertEqual(preview["viewer"]["rank"], 5)
        self.assertTrue(preview["gap_before_viewer"])
