"""Admin reseed (replace) for single-elimination brackets."""

import json

from django.test import Client, TestCase

from brackets.models import (
    BracketChallenge,
    BracketContestant,
    BracketStage,
    Contestant,
    Matchup,
    User,
)
from brackets.utils.bracket_factory import create_bracket_with_structure


class BracketReseedTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username="admin", password="x", is_staff=True
        )
        self.client.force_login(self.admin)
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "reseed-cup", "Reseed Cup", 4, self.admin
        )
        self.contestants = [
            Contestant.objects.create(
                identifier=f"team-{i + 1}",
                name=f"Team {i + 1}",
                created_by=self.admin,
            )
            for i in range(4)
        ]

    def _assign(self, pairs, replace=False):
        return self.client.post(
            f"/brackets/api/admin/brackets/{self.bracket.id}/contestants",
            data=json.dumps(
                {
                    "assignments": [
                        {"contestant_id": cid, "seed": seed}
                        for cid, seed in pairs
                    ],
                    "replace": replace,
                }
            ),
            content_type="application/json",
        )

    def _first_round(self):
        first_ko = (
            self.bracket.stages.filter(
                stage_type=BracketStage.StageType.KNOCKOUT
            )
            .order_by("order")
            .first()
        )
        master = self.bracket.get_master_bracket()
        m = Matchup.objects.get(
            user_bracket=master, stage=first_ko, position=1
        )
        return m

    def test_reseed_rebuilds_first_round(self):
        c = self.contestants
        res = self._assign(
            [(c[0].id, 1), (c[1].id, 2), (c[2].id, 3), (c[3].id, 4)]
        )
        self.assertEqual(res.status_code, 200)
        # n=4 pairs: position 1 is seed 1 vs seed 4.
        m = self._first_round()
        self.assertEqual(m.contestant1.contestant_id, c[0].id)
        self.assertEqual(m.contestant2.contestant_id, c[3].id)

        # Reseed: swap seeds 1 and 4.
        res = self._assign(
            [(c[0].id, 4), (c[1].id, 3), (c[2].id, 2), (c[3].id, 1)],
            replace=True,
        )
        self.assertEqual(res.status_code, 200)
        m = self._first_round()
        self.assertEqual(m.contestant1.contestant_id, c[3].id)
        self.assertEqual(m.contestant2.contestant_id, c[0].id)
        self.assertEqual(
            BracketContestant.objects.filter(bracket=self.bracket).count(), 4
        )

    def test_replace_drops_removed_contestants(self):
        c = self.contestants
        self._assign(
            [(c[0].id, 1), (c[1].id, 2), (c[2].id, 3), (c[3].id, 4)]
        )
        extra = Contestant.objects.create(
            identifier="team-5", name="Team 5", created_by=self.admin
        )
        res = self._assign(
            [(c[0].id, 1), (c[1].id, 2), (c[2].id, 3), (extra.id, 4)],
            replace=True,
        )
        self.assertEqual(res.status_code, 200)
        ids = set(
            BracketContestant.objects.filter(
                bracket=self.bracket
            ).values_list("contestant_id", flat=True)
        )
        self.assertEqual(ids, {c[0].id, c[1].id, c[2].id, extra.id})

    def test_reseed_blocked_when_challenge_exists(self):
        c = self.contestants
        self._assign(
            [(c[0].id, 1), (c[1].id, 2), (c[2].id, 3), (c[3].id, 4)]
        )
        BracketChallenge.objects.create(
            name="Pool", bracket=self.bracket, created_by=self.admin
        )
        res = self._assign(
            [(c[0].id, 4), (c[1].id, 3), (c[2].id, 2), (c[3].id, 1)],
            replace=True,
        )
        self.assertEqual(res.status_code, 409)
