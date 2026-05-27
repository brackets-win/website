"""Peers' brackets and stats stay hidden until the viewer submits."""

import json

from django.test import Client, TestCase
from django.utils import timezone

from brackets.models import (
    BracketChallenge,
    BracketContestant,
    ChallengeParticipant,
    User,
    UserBracket,
)
from brackets.utils.bracket_factory import create_bracket_with_structure


class ChallengePeerPrivacyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="x")
        self.viewer = User.objects.create_user(username="viewer", password="x")
        self.peer = User.objects.create_user(username="peer", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "peer-privacy",
            "Privacy Cup",
            4,
            self.host,
        )
        for i in range(4):
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
        self.challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=self.bracket,
            created_by=self.host,
        )
        self.peer_ub = UserBracket.objects.create(
            bracket=self.bracket,
            user=self.peer,
            challenge=self.challenge,
            is_master=False,
            submitted_at=timezone.now(),
        )
        self.viewer_ub = UserBracket.objects.create(
            bracket=self.bracket,
            user=self.viewer,
            challenge=self.challenge,
            is_master=False,
        )
        ChallengeParticipant.objects.create(
            challenge=self.challenge, user=self.peer
        )
        ChallengeParticipant.objects.create(
            challenge=self.challenge, user=self.viewer
        )

    def test_stats_forbidden_before_viewer_submits(self):
        self.client.force_login(self.viewer)
        res = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}/stats"
        )
        self.assertEqual(res.status_code, 403)

    def test_peer_bracket_forbidden_before_viewer_submits(self):
        self.client.force_login(self.viewer)
        res = self.client.get(
            f"/brackets/api/user-brackets/{self.peer_ub.id}"
        )
        self.assertEqual(res.status_code, 403)

    def test_peer_bracket_and_stats_allowed_after_viewer_submits(self):
        self.viewer_ub.submitted_at = timezone.now()
        self.viewer_ub.save(update_fields=["submitted_at"])
        self.client.force_login(self.viewer)
        stats = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}/stats"
        )
        self.assertEqual(stats.status_code, 200)
        detail = self.client.get(
            f"/brackets/api/user-brackets/{self.peer_ub.id}"
        )
        self.assertEqual(detail.status_code, 200)

    def test_challenge_summary_flags_peer_access(self):
        self.client.force_login(self.viewer)
        res = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["challenge"]
        self.assertFalse(data["can_view_peer_brackets"])

        self.viewer_ub.submitted_at = timezone.now()
        self.viewer_ub.save(update_fields=["submitted_at"])
        res2 = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}"
        )
        self.assertTrue(res2.json()["challenge"]["can_view_peer_brackets"])
