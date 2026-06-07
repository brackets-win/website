"""Scoring highlights visible to challenge participants viewing others' brackets."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.api.serializers import user_bracket_detail
from brackets.models import BracketChallenge, ChallengeParticipant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure

User = get_user_model()


class ScoringHighlightsViewerTests(TestCase):
    def test_participant_sees_highlights_on_another_entry(self):
        host = User.objects.create_user(username="host", password="x")
        viewer = User.objects.create_user(username="viewer", password="x")
        other = User.objects.create_user(username="other", password="x")
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "hl-view", "V", 8, host
        )
        challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=bracket,
            created_by=host,
        )
        for u in (viewer, other):
            ChallengeParticipant.objects.create(challenge=challenge, user=u)
        other_ub = UserBracket.objects.create(
            user=other,
            bracket=bracket,
            challenge=challenge,
            display_name="Other",
        )
        payload = user_bracket_detail(other_ub, viewer=viewer)
        self.assertIn("scoring_highlights", payload)
