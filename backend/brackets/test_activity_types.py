"""Bracket challenge instance types: tournament vs bracket challenge enrollment."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.models import BracketChallenge, ChallengeParticipant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.challenge_deadline import assert_can_join
from brackets.utils.challenge_types import TOURNAMENT

User = get_user_model()


class ActivityTypeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="host", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "act-se", "Act SE", 4, self.user
        )

    def test_tournament_join_without_user_bracket(self):
        challenge = BracketChallenge.objects.create(
            name="Friends cup",
            bracket=self.bracket,
            instance_type=TOURNAMENT,
            created_by=self.user,
            is_public=True,
        )
        assert_can_join(challenge)
        ChallengeParticipant.objects.create(challenge=challenge, user=self.user)
        self.assertFalse(
            UserBracket.objects.filter(
                user=self.user, challenge=challenge, is_master=False
            ).exists()
        )
