"""Challenge participants can read (not edit) the master bracket."""

import json

from django.test import Client, TestCase

from brackets.models import BracketChallenge, BracketContestant, User, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure


class MasterBracketViewApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="secret")
        self.player = User.objects.create_user(username="player", password="secret")
        self.outsider = User.objects.create_user(username="outsider", password="secret")
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
