"""Admin challenge catalog and staff fill-on-behalf-of-user."""

import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from brackets.models import (
    BracketChallenge,
    BracketContestant,
    ChallengeParticipant,
    Matchup,
    User,
    UserBracket,
)
from brackets.utils.bracket_factory import create_bracket_with_structure


class AdminChallengesApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username="admin",
            password="staff-pass-123",
            is_staff=True,
        )
        self.player = User.objects.create_user(
            username="player",
            password="player-pass-123",
        )
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "hist-cup",
            "Historical Cup",
            4,
            self.staff,
        )
        for i in range(4):
            BracketContestant.objects.create(
                bracket=self.bracket,
                name_override=f"T{i + 1}",
                seed=i + 1,
            )
        self.bracket.ensure_master_bracket()
        self.past_deadline = timezone.now() - timedelta(days=30)

    def _login_staff(self):
        self.client.force_login(self.staff)

    def test_list_requires_staff(self):
        self.client.force_login(self.player)
        res = self.client.get("/brackets/api/admin/challenges")
        self.assertEqual(res.status_code, 403)

    def test_create_list_and_delete_challenge(self):
        self._login_staff()
        create = self.client.post(
            "/brackets/api/admin/challenges",
            data=json.dumps(
                {
                    "name": "2018 Pool",
                    "bracket_id": self.bracket.id,
                    "submission_deadline": self.past_deadline.isoformat(),
                    "max_entries": 1,
                    "is_private": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create.status_code, 201)
        challenge_id = create.json()["challenge"]["id"]
        self.assertTrue(create.json()["challenge"]["is_private"])
        self.assertTrue(create.json()["challenge"]["deadline_passed"])
        # Admin create does not auto-enroll the staff user.
        self.assertFalse(
            ChallengeParticipant.objects.filter(
                challenge_id=challenge_id, user=self.staff
            ).exists()
        )

        listed = self.client.get("/brackets/api/admin/challenges")
        self.assertEqual(listed.status_code, 200)
        ids = {row["id"] for row in listed.json()["challenges"]}
        self.assertIn(challenge_id, ids)

        impact = self.client.get(
            f"/brackets/api/admin/delete-impact/challenge/{challenge_id}"
        )
        self.assertEqual(impact.status_code, 200)

        deleted = self.client.delete(
            f"/brackets/api/admin/challenges/{challenge_id}"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(
            BracketChallenge.objects.filter(id=challenge_id).exists()
        )

    def test_staff_can_enroll_and_submit_past_deadline(self):
        self._login_staff()
        challenge = BracketChallenge.objects.create(
            name="Old Season",
            bracket=self.bracket,
            created_by=self.staff,
            submission_deadline=self.past_deadline,
            max_entries=1,
        )

        entry = self.client.post(
            f"/brackets/api/admin/challenges/{challenge.id}/entries",
            data=json.dumps(
                {
                    "user_id": self.player.id,
                    "display_name": "Player One",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(entry.status_code, 201)
        ub_payload = entry.json()["entry"]
        ub_id = ub_payload["user_bracket_id"]
        self.assertEqual(ub_payload["user_id"], self.player.id)

        listed = self.client.get(
            f"/brackets/api/admin/challenges/{challenge.id}/entries"
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["entries"]), 1)

        renamed = self.client.patch(
            f"/brackets/api/admin/challenges/{challenge.id}/entries/{ub_id}",
            data=json.dumps({"display_name": "Renamed Player"}),
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["entry"]["display_name"], "Renamed Player")

        detail = self.client.get(f"/brackets/api/admin/user-brackets/{ub_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["user_bracket"]["can_edit"])

        ub = UserBracket.objects.get(pk=ub_id)
        matchups = list(Matchup.objects.filter(user_bracket=ub).order_by("id"))
        self.assertGreater(len(matchups), 0)

        # Fill all matchups so the bracket is complete enough to submit.
        # Walk leaf → root by setting winners where both slots are filled.
        for _ in range(10):
            pending = Matchup.objects.filter(
                user_bracket=ub,
                winner_id__isnull=True,
                contestant1_id__isnull=False,
                contestant2_id__isnull=False,
            )
            progressed = False
            for m in pending:
                pick = self.client.patch(
                    f"/brackets/api/matchups/{m.id}",
                    data=json.dumps({"winner_id": m.contestant1_id}),
                    content_type="application/json",
                )
                self.assertEqual(pick.status_code, 200)
                progressed = True
            if not progressed:
                break

        submit = self.client.post(f"/brackets/api/user-brackets/{ub_id}/submit")
        self.assertEqual(submit.status_code, 200)
        ub.refresh_from_db()
        self.assertIsNotNone(ub.submitted_at)

    def test_player_cannot_edit_past_deadline(self):
        challenge = BracketChallenge.objects.create(
            name="Closed",
            bracket=self.bracket,
            created_by=self.staff,
            submission_deadline=self.past_deadline,
        )
        ub = UserBracket.objects.create(
            user=self.player,
            bracket=self.bracket,
            challenge=challenge,
            is_master=False,
            display_name="Player",
        )
        ChallengeParticipant.objects.create(challenge=challenge, user=self.player)
        from brackets.utils.knockout_tree import (
            ensure_knockout_structure_for_user_bracket,
        )

        ensure_knockout_structure_for_user_bracket(ub)
        m = Matchup.objects.filter(
            user_bracket=ub,
            contestant1_id__isnull=False,
            contestant2_id__isnull=False,
        ).first()
        self.assertIsNotNone(m)

        self.client.force_login(self.player)
        res = self.client.patch(
            f"/brackets/api/matchups/{m.id}",
            data=json.dumps({"winner_id": m.contestant1_id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
