"""Challenge participants can read (not edit) the master bracket."""

import json

from django.test import Client, TestCase

from brackets.models import BracketChallenge, BracketContestant, User, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket
from brackets.utils.leaderboard_scoring import materialize_leaderboard_scores_for_bracket


class MasterBracketViewApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="secret")
        self.player = User.objects.create_user(username="player", password="secret")
        self.outsider = User.objects.create_user(username="outsider", password="secret")
        self.staff = User.objects.create_superuser(
            username="staff", email="s@example.com", password="secret"
        )
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "view-master",
            "Cup",
            4,
            self.host,
        )
        for i in range(4):
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
        self.master = UserBracket.objects.get(bracket=self.bracket, is_master=True)
        self.challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=self.bracket,
            created_by=self.host,
            join_code="POOL2026",
        )

    def _join(self, user: User):
        self.client.force_login(user)
        return self.client.post(
            "/brackets/api/challenges/join",
            data=json.dumps(
                {"join_code": "POOL2026", "display_name": "Test Player"}
            ),
            content_type="application/json",
        )

    def test_challenge_includes_master_id_for_participant(self):
        res = self._join(self.player)
        self.assertEqual(res.status_code, 200)
        ch = res.json()["challenge"]
        self.assertEqual(ch["master_user_bracket_id"], self.master.id)

    def test_participant_can_get_master_bracket(self):
        self._join(self.player)
        self.client.force_login(self.player)
        res = self.client.get(f"/brackets/api/user-brackets/{self.master.id}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["user_bracket"]["is_master"])

    def test_outsider_cannot_get_master_bracket(self):
        self.client.force_login(self.outsider)
        res = self.client.get(f"/brackets/api/user-brackets/{self.master.id}")
        self.assertEqual(res.status_code, 403)

    def test_participant_cannot_patch_master_bracket(self):
        self._join(self.player)
        self.client.force_login(self.player)
        res = self.client.patch(
            f"/brackets/api/user-brackets/{self.master.id}",
            data=json.dumps({"group_positions": {}}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

    def test_staff_master_pick_sets_pending_until_materialized(self):
        teams = list(
            BracketContestant.objects.filter(bracket=self.bracket).order_by(
                "seed", "id"
            )
        )
        ensure_knockout_structure_for_user_bracket(self.master)
        matchup = self.master.matchup_set.order_by("stage__order", "position").first()
        self.assertIsNotNone(matchup)
        matchup.contestant1 = teams[0]
        matchup.contestant2 = teams[1]
        matchup.save(update_fields=["contestant1", "contestant2"])
        winner_id = teams[0].id

        self.client.force_login(self.staff)
        res = self.client.patch(
            f"/brackets/api/matchups/{matchup.id}",
            data=json.dumps({"winner_id": winner_id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        res = self.client.get(f"/brackets/api/user-brackets/{self.master.id}")
        self.assertTrue(res.json()["user_bracket"]["leaderboard_scores_pending"])

        res = self.client.post(
            f"/brackets/api/brackets/{self.bracket.id}/materialize-scores"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["leaderboard_scores_pending"])
        self.assertEqual(body["remaining_count"], 0)

        res = self.client.get(f"/brackets/api/user-brackets/{self.master.id}")
        self.assertFalse(res.json()["user_bracket"]["leaderboard_scores_pending"])
