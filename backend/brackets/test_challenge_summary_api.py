"""Regression: challenge_summary must not raise when building list payloads."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.api.serializers import challenge_summary
from brackets.models import BracketChallenge
from brackets.utils.bracket_factory import create_bracket_with_structure

User = get_user_model()


class ChallengeSummaryApiTests(TestCase):
    def test_challenge_summary_for_bracket_challenge(self):
        host = User.objects.create_user(username="host", password="x")
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "sum-test",
            "Sum",
            8,
            host,
        )
        challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=bracket,
            created_by=host,
        )
        payload = challenge_summary(challenge)
        self.assertEqual(payload["instance_type"], "CHALLENGE")
        self.assertEqual(payload["created_by_username"], "host")
        self.assertEqual(payload["max_entries"], 1)
        self.assertEqual(payload["user_entries"], [])
        self.assertIn("deadline_passed", payload)
