"""Group results mode on bracket metadata."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.models import Bracket, UserBracket
from brackets.utils.group_results_mode import group_results_mode_from_metadata

User = get_user_model()


class GroupResultsModeApiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff", password="pw", is_staff=True
        )
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
