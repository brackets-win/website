"""Group results mode on bracket metadata."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import Bracket, BracketChallenge, BracketContestant, User, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.group_results_mode import (
    group_results_mode_from_metadata,
    master_has_group_results,
    omit_leaderboard_potential_for_bracket,
    set_group_results_mode_on_metadata,
)
from brackets.utils.leaderboard_scoring import refresh_user_bracket_leaderboard_cache

User = get_user_model()


class GroupResultsModeApiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        self.player = User.objects.create_user(username="player", password="pw")
        self.bracket = Bracket.objects.create(
            identifier="wc-live",
            name="WC Live",
            created_by=self.staff,
            is_reusable=True,
        )
        self.master = UserBracket.objects.get(bracket=self.bracket, is_master=True)

    def test_staff_can_set_live_mode(self):
        self.client.login(username="staff", password="pw")
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/group-results-mode",
            data=json.dumps({"group_results_mode": "live"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.bracket.refresh_from_db()
        self.assertEqual(
            group_results_mode_from_metadata(self.bracket.metadata), "live"
        )

    def test_rejects_invalid_mode(self):
        self.client.login(username="staff", password="pw")
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/group-results-mode",
            data=json.dumps({"group_results_mode": "maybe"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_live_mode_omits_potential_from_leaderboard_and_materialize(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "live-potential",
            "Live Potential",
            8,
            self.staff,
        )
        for i in range(8):
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"T{i + 1}", seed=i + 1
            )
        bracket.metadata = set_group_results_mode_on_metadata(bracket.metadata, "live")
        bracket.save(update_fields=["metadata"])

        challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=bracket,
            created_by=self.staff,
            join_code="LIVEPOT1",
        )
        ub = UserBracket.objects.create(
            user=self.player,
            bracket=bracket,
            challenge=challenge,
            submitted_at=timezone.now(),
            leaderboard_potential=42,
        )
        refresh_user_bracket_leaderboard_cache(ub)
        ub.refresh_from_db()
        self.assertEqual(ub.leaderboard_potential, 42)

        self.client.login(username="player", password="pw")
        res = self.client.get(f"/brackets/api/challenges/{challenge.id}/leaderboard")
        self.assertEqual(res.status_code, 200)
        keys = [c["key"] for c in res.json()["columns"]]
        self.assertNotIn("potential", keys)
        self.assertIsNone(res.json()["entries"][0]["potential"])

    def test_empty_master_omits_potential_even_when_mode_is_confirmed(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "empty-potential",
            "Empty Potential",
            8,
            self.staff,
        )
        for i in range(8):
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"T{i + 1}", seed=i + 1
            )
        self.assertEqual(
            group_results_mode_from_metadata(bracket.metadata), "confirmed"
        )
        self.assertFalse(master_has_group_results(bracket))
        self.assertTrue(omit_leaderboard_potential_for_bracket(bracket))

        challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=bracket,
            created_by=self.staff,
            join_code="EMPTYPOT",
        )
        UserBracket.objects.create(
            user=self.player,
            bracket=bracket,
            challenge=challenge,
            submitted_at=timezone.now(),
            leaderboard_potential=48,
        )

        self.client.login(username="player", password="pw")
        res = self.client.get(f"/brackets/api/challenges/{challenge.id}/leaderboard")
        self.assertEqual(res.status_code, 200)
        keys = [c["key"] for c in res.json()["columns"]]
        self.assertNotIn("potential", keys)
        self.assertNotIn("potential_rank", keys)
        self.assertIsNone(res.json()["entries"][0]["potential"])

    def test_confirmed_with_group_results_shows_potential(self):
        from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket
        from brackets.utils.sync_group_knockout import sync_first_knockout_from_group_picks

        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "confirmed-potential",
            "Confirmed Potential",
            8,
            self.staff,
        )
        teams = [
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(8)
        ]
        master = bracket.get_master_bracket()
        ensure_knockout_structure_for_user_bracket(master)
        master.metadata = {
            "group_positions": {
                "A": {str(i + 1): teams[i].id for i in range(4)},
                "B": {str(i + 1): teams[i + 4].id for i in range(4)},
            }
        }
        master.save(update_fields=["metadata"])
        sync_first_knockout_from_group_picks(master)
        bracket.metadata = set_group_results_mode_on_metadata(
            bracket.metadata, "confirmed"
        )
        bracket.save(update_fields=["metadata"])

        self.assertTrue(master_has_group_results(bracket))
        self.assertFalse(omit_leaderboard_potential_for_bracket(bracket))

        challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=bracket,
            created_by=self.staff,
            join_code="CONFPOT1",
        )
        UserBracket.objects.create(
            user=self.player,
            bracket=bracket,
            challenge=challenge,
            submitted_at=timezone.now(),
            leaderboard_potential=48,
        )

        self.client.login(username="player", password="pw")
        res = self.client.get(f"/brackets/api/challenges/{challenge.id}/leaderboard")
        self.assertEqual(res.status_code, 200)
        keys = [c["key"] for c in res.json()["columns"]]
        self.assertIn("potential", keys)
