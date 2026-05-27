"""API tests for challenge join."""

import json

from django.test import Client, TestCase

from brackets.models import (
    Bracket,
    BracketChallenge,
    BracketContestant,
    ChallengeParticipant,
    Matchup,
    User,
    UserBracket,
)
from brackets.utils.bracket_factory import create_bracket_with_structure


class ChallengeJoinApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.creator = User.objects.create_user(username="host", password="secret")
        self.joiner = User.objects.create_user(username="guest", password="secret")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "office-cup",
            "Cup",
            4,
            self.creator,
        )
        for i in range(4):
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
        self.challenge = BracketChallenge.objects.create(
            name="Office pool",
            bracket=self.bracket,
            created_by=self.creator,
            join_code="POOL2026",
        )

    def _post_join(self, user: User, code: str):
        self.client.force_login(user)
        return self.client.post(
            "/brackets/api/challenges/join",
            data=json.dumps({"join_code": code, "display_name": "Guest Player"}),
            content_type="application/json",
        )

    def test_join_creates_participant_and_user_bracket(self):
        res = self._post_join(self.joiner, "pool2026")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["challenge"]["id"], self.challenge.id)
        ub_id = data["challenge"]["user_bracket_id"]
        self.assertIsNotNone(ub_id)
        self.assertTrue(
            ChallengeParticipant.objects.filter(
                challenge=self.challenge, user=self.joiner
            ).exists()
        )
        ub = UserBracket.objects.get(pk=ub_id)
        self.assertEqual(ub.user_id, self.joiner.id)
        self.assertEqual(ub.challenge_id, self.challenge.id)

    def test_join_invalid_code(self):
        res = self._post_join(self.joiner, "NOPE")
        self.assertEqual(res.status_code, 404)

    def test_join_requires_auth(self):
        res = self.client.post(
            "/brackets/api/challenges/join",
            data=json.dumps(
                {"join_code": "POOL2026", "display_name": "Guest"}
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

    def test_join_is_idempotent(self):
        first = self._post_join(self.joiner, "POOL2026")
        second = self._post_join(self.joiner, "POOL2026")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            first.json()["challenge"]["user_bracket_id"],
            second.json()["challenge"]["user_bracket_id"],
        )
        self.assertEqual(
            ChallengeParticipant.objects.filter(
                challenge=self.challenge, user=self.joiner
            ).count(),
            1,
        )

    def test_creator_can_delete_challenge(self):
        self.client.force_login(self.creator)
        res = self.client.delete(
            f"/brackets/api/challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            BracketChallenge.objects.filter(pk=self.challenge.pk).exists()
        )

    def test_non_creator_cannot_delete_challenge(self):
        self._post_join(self.joiner, "POOL2026")
        self.client.force_login(self.joiner)
        res = self.client.delete(
            f"/brackets/api/challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 403)
        self.assertTrue(
            BracketChallenge.objects.filter(pk=self.challenge.pk).exists()
        )

    def test_create_tournament_builds_master_knockout_shell(self):
        self.client.force_login(self.creator)
        res = self.client.post(
            "/brackets/api/challenges",
            data=json.dumps(
                {
                    "name": "Test Tourney",
                    "instance_type": "TOURNAMENT",
                    "bracket_setup": {
                        "structure": "SINGLE_ELIM",
                        "identifier": "test-tourney-shell",
                        "bracket_name": "Test Tourney",
                        "number_of_contestants": 8,
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        payload = res.json()["challenge"]
        master_id = payload.get("master_user_bracket_id")
        self.assertIsNotNone(master_id)
        self.assertIsNone(payload.get("user_bracket_id"))
        self.assertGreater(
            Matchup.objects.filter(user_bracket_id=master_id).count(), 0
        )

    def test_create_tournament_reuses_taken_identifier_with_suffix(self):
        self.client.force_login(self.creator)
        payload = {
            "name": "Repeat Tourney",
            "instance_type": "TOURNAMENT",
            "bracket_setup": {
                "structure": "SINGLE_ELIM",
                "identifier": "repeat-tourney",
                "bracket_name": "Repeat Tourney",
                "number_of_contestants": 8,
            },
        }
        first = self.client.post(
            "/brackets/api/challenges",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            "/brackets/api/challenges",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 201)
        ids = list(
            Bracket.objects.filter(identifier__startswith="repeat-tourney").values_list(
                "identifier", flat=True
            )
        )
        self.assertIn("repeat-tourney", ids)
        self.assertIn("repeat-tourney-2", ids)
