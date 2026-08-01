"""Knockout fill gating for tournament master group results."""

import json

from django.test import Client, TestCase

from brackets.models import BracketContestant, Contestant, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.group_fixtures import generate_round_robin
from brackets.utils.group_knockout_fill import SEEDING, ensure_knockout_fill_method_persisted
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell
from brackets.utils.results_entry import merge_results_entry_into_metadata
from brackets.utils.sync_group_knockout import sync_first_knockout_from_group_picks


class MasterKnockoutFillGatingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="host", password="x")
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "gk-gate-test",
            "Gate Test",
            16,
            self.user,
            structure_config={
                "results_entry": {"group": "standings", "knockout": "winner"},
            },
        )
        self.contestants: list[BracketContestant] = []
        for i in range(16):
            c = Contestant.objects.create(
                identifier=f"g{i}",
                name=f"Team {i}",
                created_by=self.user,
            )
            self.contestants.append(
                BracketContestant.objects.create(
                    bracket=self.bracket, contestant=c, seed=i + 1
                )
            )
        self.master = self.bracket.get_master_bracket()
        ensure_knockout_matchup_shell(self.master)
        self.client = Client()
        self.client.force_login(self.user)

    def _g(self):
        return {
            "A": [self.contestants[i].id for i in range(0, 4)],
            "B": [self.contestants[i].id for i in range(4, 8)],
            "C": [self.contestants[i].id for i in range(8, 12)],
            "D": [self.contestants[i].id for i in range(12, 16)],
        }

    def _full_positions(self):
        g = self._g()
        return {
            code: {"1": ids[0], "2": ids[1]}
            for code, ids in g.items()
        }

    def test_standings_without_complete_does_not_fill_ko(self):
        g = self._g()
        res = self.client.patch(
            f"/brackets/api/user-brackets/{self.master.id}",
            data=json.dumps({"group_positions": self._full_positions()}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        m1 = Matchup.objects.get(
            user_bracket=self.master, stage=first_ko, position=1
        )
        self.assertIsNone(m1.contestant1_id)
        self.assertIsNone(m1.contestant2_id)

    def test_complete_group_stage_fills_ko(self):
        g = self._g()
        res = self.client.patch(
            f"/brackets/api/user-brackets/{self.master.id}",
            data=json.dumps(
                {
                    "group_positions": self._full_positions(),
                    "group_stage_completed": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        m1 = Matchup.objects.get(
            user_bracket=self.master, stage=first_ko, position=1
        )
        self.assertEqual(m1.contestant1_id, g["A"][0])
        self.assertEqual(m1.contestant2_id, g["B"][1])

    def test_fixtures_standard_fills_completed_group_only(self):
        self.bracket.metadata = merge_results_entry_into_metadata(
            self.bracket.metadata, {"group": "table", "knockout": "winner"}
        )
        self.bracket.save(update_fields=["metadata"])
        g = self._g()
        fixtures_a = generate_round_robin(
            g["A"], matches_per_contestant=3, group_code="A"
        )
        # Finish only group A: round-robin of 4 = 6 matches.
        scores = [(2, 0), (1, 0), (3, 1), (2, 1), (1, 0), (2, 2)]
        for row, (hs, aws) in zip(fixtures_a, scores):
            row["home_score"] = hs
            row["away_score"] = aws
        fixtures_b = generate_round_robin(
            g["B"], matches_per_contestant=3, group_code="B"
        )
        res = self.client.patch(
            f"/brackets/api/user-brackets/{self.master.id}",
            data=json.dumps(
                {"group_fixtures": {"A": fixtures_a, "B": fixtures_b}}
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        m1 = Matchup.objects.get(
            user_bracket=self.master, stage=first_ko, position=1
        )
        # A1 vs B2 — A ready, B not → A1 filled, B2 empty.
        self.assertIsNotNone(m1.contestant1_id)
        self.assertIsNone(m1.contestant2_id)

    def test_fixtures_seeding_waits_for_all_groups(self):
        self.bracket.metadata = merge_results_entry_into_metadata(
            self.bracket.metadata, {"group": "table", "knockout": "winner"}
        )
        self.bracket.save(update_fields=["metadata"])
        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        ensure_knockout_fill_method_persisted(first_ko, self.bracket, method=SEEDING)

        g = self._g()
        fixtures = {}
        for code, ids in g.items():
            rows = generate_round_robin(ids, matches_per_contestant=3, group_code=code)
            if code != "D":
                for i, row in enumerate(rows):
                    row["home_score"] = 1 if i % 2 == 0 else 0
                    row["away_score"] = 0 if i % 2 == 0 else 1
            fixtures[code] = rows

        res = self.client.patch(
            f"/brackets/api/user-brackets/{self.master.id}",
            data=json.dumps({"group_fixtures": fixtures}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        m1 = Matchup.objects.get(
            user_bracket=self.master, stage=first_ko, position=1
        )
        self.assertIsNone(m1.contestant1_id)
        self.assertIsNone(m1.contestant2_id)

        # Finish D, then KO fills.
        for i, row in enumerate(fixtures["D"]):
            row["home_score"] = 1 if i % 2 == 0 else 0
            row["away_score"] = 0 if i % 2 == 0 else 1
        res = self.client.patch(
            f"/brackets/api/user-brackets/{self.master.id}",
            data=json.dumps({"group_fixtures": fixtures}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        m1.refresh_from_db()
        self.assertIsNotNone(m1.contestant1_id)
        self.assertIsNotNone(m1.contestant2_id)
