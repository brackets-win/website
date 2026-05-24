"""Multiple entries per user when max_entries > 1."""

import json

from django.test import Client, TestCase

from brackets.models import (
    BracketChallenge,
    BracketContestant,
    User,
    UserBracket,
)
from brackets.utils.bracket_factory import create_bracket_with_structure


class ChallengeMaxEntriesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="secret")
        self.player = User.objects.create_user(username="guest", password="secret")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "multi-entry",
            "Cup",
            4,
            self.host,
        )
        for i in range(4):
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
        self.challenge = BracketChallenge.objects.create(
            name="Multi pool",
            bracket=self.bracket,
            created_by=self.host,
            join_code="MULTI123",
            max_entries=3,
        )

    def _join(self, user: User, display_name: str):
        self.client.force_login(user)
        return self.client.post(
            "/brackets/api/challenges/join",
            data=json.dumps(
                {"join_code": "MULTI123", "display_name": display_name}
            ),
            content_type="application/json",
        )

    def test_multiple_entries_with_distinct_names(self):
        r1 = self._join(self.player, "Alice")
        r2 = self._join(self.player, "Bob")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertNotEqual(
            r1.json()["challenge"]["user_bracket_id"],
            r2.json()["challenge"]["user_bracket_id"],
        )
        self.assertEqual(
            UserBracket.objects.filter(
                user=self.player, challenge=self.challenge, is_master=False
            ).count(),
            2,
        )

    def test_duplicate_display_name_rejected(self):
        self._join(self.player, "Alice")
        res = self._join(self.player, "alice")
        self.assertEqual(res.status_code, 400)

    def test_max_entries_blocks_extra_join(self):
        self._join(self.player, "One")
        self._join(self.player, "Two")
        self._join(self.player, "Three")
        res = self._join(self.player, "Four")
        self.assertEqual(res.status_code, 400)

    def test_creator_can_raise_max_entries(self):
        self.client.force_login(self.host)
        res = self.client.patch(
            f"/brackets/api/challenges/{self.challenge.id}",
            data=json.dumps({"max_entries": 5}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.max_entries, 5)
        self.assertEqual(res.json()["challenge"]["max_entries"], 5)

    def test_creator_cannot_lower_max_entries_below_usage(self):
        self._join(self.player, "One")
        self._join(self.player, "Two")
        self.client.force_login(self.host)
        res = self.client.patch(
            f"/brackets/api/challenges/{self.challenge.id}",
            data=json.dumps({"max_entries": 1}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.max_entries, 3)

    def test_non_creator_cannot_patch_max_entries(self):
        self.client.force_login(self.player)
        res = self.client.patch(
            f"/brackets/api/challenges/{self.challenge.id}",
            data=json.dumps({"max_entries": 5}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
