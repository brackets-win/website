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
    bracket_challenge_leaderboard_previews,
    streak_challenge_leaderboard_preview,
)
from brackets.utils.leaderboard_scoring import (
    refresh_all_submitted_leaderboard_scores_for_bracket,
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
        refresh_all_submitted_leaderboard_scores_for_bracket(bracket)

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
            streak_challenge=challenge,
            user=u1,
            display_name="Player One",
            wins=3,
            losses=1,
            streak_signed=2,
            best_win_streak=4,
        )
        StreakParticipant.objects.create(
            streak_challenge=challenge,
            user=u2,
            display_name="Player Two",
            wins=1,
            losses=2,
            streak_signed=-1,
            best_win_streak=1,
        )
        preview = streak_challenge_leaderboard_preview(challenge, u1)
        self.assertEqual(preview["top"][0]["display_name"], "Player One")
        self.assertEqual(preview["top"][0]["points_label"], "4W")
        self.assertTrue(preview["top"][0]["is_viewer"])
        self.assertIsNone(preview["viewer"])

    def test_streak_preview_ungraded_players_share_rank_one(self):
        host = User.objects.create_user(username="host", password="x")
        competition = StreakCompetition.objects.create(name="Streak comp")
        challenge = StreakChallenge.objects.create(
            name="Streak",
            streak_competition=competition,
            created_by=host,
            is_public=True,
        )
        names = ["Keaton", "coley2007", "trady_baylor", "jfigueroa17"]
        for name in names:
            user = User.objects.create_user(username=name, password="x")
            StreakParticipant.objects.create(
                streak_challenge=challenge,
                user=user,
                display_name=name,
            )
        preview = streak_challenge_leaderboard_preview(challenge, host, limit=10)
        ranks = [row["rank"] for row in preview["top"]]
        self.assertEqual(ranks, [1, 1, 1, 1])
        display_names = [row["display_name"] for row in preview["top"]]
        self.assertEqual(
            display_names,
            sorted(names, key=str.casefold),
        )

    def test_streak_preview_uses_better_worst_streak_as_final_tiebreaker(self):
        host = User.objects.create_user(username="host", password="x")
        u1 = User.objects.create_user(username="low_loss", password="x")
        u2 = User.objects.create_user(username="high_loss", password="x")
        competition = StreakCompetition.objects.create(name="Streak comp")
        challenge = StreakChallenge.objects.create(
            name="Streak",
            streak_competition=competition,
            created_by=host,
            is_public=True,
        )
        for user, display_name, best_loss in (
            (u1, "Low Loss", 1),
            (u2, "High Loss", 4),
        ):
            StreakParticipant.objects.create(
                streak_challenge=challenge,
                user=user,
                display_name=display_name,
                wins=6,
                losses=4,
                streak_signed=2,
                best_win_streak=3,
                best_loss_streak=best_loss,
            )

        preview = streak_challenge_leaderboard_preview(challenge, host, limit=2)
        self.assertEqual(preview["top"][0]["display_name"], "Low Loss")
        self.assertEqual(preview["top"][0]["rank"], 1)
        self.assertEqual(preview["top"][1]["display_name"], "High Loss")
        self.assertEqual(preview["top"][1]["rank"], 2)

    def test_bracket_preview_without_master_does_not_crash(self):
        host = User.objects.create_user(username="host2", password="x")
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "no-master", "No Master", 4, host
        )
        UserBracket.objects.filter(bracket=bracket, is_master=True).delete()
        challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=bracket,
            created_by=host,
        )
        preview = bracket_challenge_leaderboard_preview(challenge, host)
        self.assertEqual(preview["top"], [])
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
                best_win_streak=max(streak, 0),
            )

        preview = streak_challenge_leaderboard_preview(challenge, viewer, limit=3)
        self.assertEqual(len(preview["top"]), 3)
        self.assertIsNotNone(preview["viewer"])
        self.assertEqual(preview["viewer"]["display_name"], "viewer")
        self.assertEqual(preview["viewer"]["rank"], 5)
        self.assertTrue(preview["gap_before_viewer"])

    def test_bracket_previews_batch_matches_single(self):
        host = User.objects.create_user(username="batch-host", password="x")
        u1 = User.objects.create_user(username="batch-alice", password="x")
        u2 = User.objects.create_user(username="batch-bob", password="x")
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "lb-batch", "Batch", 4, host
        )
        challenge = BracketChallenge.objects.create(
            name="Pool A",
            bracket=bracket,
            created_by=host,
        )
        bracket.ensure_master_bracket()

        for user, name in ((u1, "Alice"), (u2, "Bob")):
            ub = UserBracket.objects.create(
                user=user,
                bracket=bracket,
                challenge=challenge,
                display_name=name,
            )
            ub.submitted_at = timezone.now()
            ub.save(update_fields=["submitted_at"])
        refresh_all_submitted_leaderboard_scores_for_bracket(bracket)

        single = bracket_challenge_leaderboard_preview(challenge, u1)
        batch = bracket_challenge_leaderboard_previews([challenge], u1)[challenge.id]
        self.assertEqual(single, batch)
