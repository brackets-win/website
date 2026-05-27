"""Reusable vs one-off (tournament/poll) brackets."""

import json

from django.test import Client, TestCase

from brackets.models import Bracket, BracketChallenge, User
from brackets.utils.bracket_factory import create_bracket_with_structure


class BracketReusabilityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="host", password="x")
        self.client.force_login(self.user)
        self.catalog = create_bracket_with_structure(
            "SINGLE_ELIM", "catalog-cup", "Catalog Cup", 4, self.user
        )

    def test_brackets_list_only_reusable(self):
        create_bracket_with_structure(
            "SINGLE_ELIM",
            "tourney-only",
            "Tourney Only",
            4,
            self.user,
            is_reusable=False,
        )
        res = self.client.get("/brackets/api/brackets")
        self.assertEqual(res.status_code, 200)
        ids = {b["id"] for b in res.json()["brackets"]}
        self.assertIn(self.catalog.id, ids)
        self.assertNotIn(
            Bracket.objects.get(identifier="tourney-only").id, ids
        )

    def test_tournament_create_marks_bracket_not_reusable(self):
        res = self.client.post(
            "/brackets/api/challenges",
            data=json.dumps(
                {
                    "name": "Friends Cup",
                    "instance_type": "TOURNAMENT",
                    "bracket_setup": {
                        "structure": "SINGLE_ELIM",
                        "identifier": "friends-cup",
                        "bracket_name": "Friends Cup",
                        "number_of_contestants": 4,
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        ch = BracketChallenge.objects.get(pk=res.json()["challenge"]["id"])
        self.assertFalse(ch.bracket.is_reusable)

    def test_challenge_rejects_non_reusable_bracket(self):
        one_off = create_bracket_with_structure(
            "SINGLE_ELIM", "one-off", "One Off", 4, self.user, is_reusable=False
        )
        res = self.client.post(
            "/brackets/api/challenges",
            data=json.dumps(
                {
                    "name": "Pool",
                    "instance_type": "CHALLENGE",
                    "bracket_id": one_off.id,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_challenge_accepts_reusable_bracket(self):
        res = self.client.post(
            "/brackets/api/challenges",
            data=json.dumps(
                {
                    "name": "Pool",
                    "instance_type": "CHALLENGE",
                    "bracket_id": self.catalog.id,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
