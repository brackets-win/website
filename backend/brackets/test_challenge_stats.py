"""Challenge stats: group averages and knockout reach percentages."""

import json

from django.test import Client, TestCase

from brackets.models import BracketChallenge, BracketContestant, KnockoutStage, User, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.challenge_stats import compute_challenge_stats
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell


class ChallengeStatsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="x")
        self.u1 = User.objects.create_user(username="u1", password="x")
        self.u2 = User.objects.create_user(username="u2", password="x")
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "stats-gk", "Stats GK", 8, self.host
        )
        self.teams = [
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(8)
        ]
        self.challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=self.bracket,
            created_by=self.host,
        )

    def _submit_with_groups(self, user, gp: dict):
        ub = UserBracket.objects.create(
            bracket=self.bracket,
            user=user,
            challenge=self.challenge,
            is_master=False,
            metadata={"group_positions": gp},
        )
        from django.utils import timezone

        ub.submitted_at = timezone.now()
        ub.save(update_fields=["submitted_at", "metadata"])
        ensure_knockout_matchup_shell(ub)
        return ub

    def test_group_average_position(self):
        # Group A: T1, T2, T3, T4
        gp_a = {"1": self.teams[0].id, "2": self.teams[1].id, "3": self.teams[2].id, "4": self.teams[3].id}
        self._submit_with_groups(
            self.u1,
            {"A": gp_a, "B": {"1": self.teams[4].id, "2": self.teams[5].id, "3": self.teams[6].id, "4": self.teams[7].id}},
        )
        gp_u2_a = {"1": self.teams[0].id, "2": self.teams[2].id, "3": self.teams[1].id, "4": self.teams[3].id}
        self._submit_with_groups(
            self.u2,
            {"A": gp_u2_a, "B": {"1": self.teams[4].id, "2": self.teams[5].id, "3": self.teams[6].id, "4": self.teams[7].id}},
        )

        stats = compute_challenge_stats(self.challenge)
        group_a = next(g for g in stats["group_stage"] if g["code"] == "A")
        t1 = next(t for t in group_a["teams"] if t["bracket_contestant_id"] == self.teams[0].id)
        self.assertEqual(t1["average_position"], 1.0)
        t2 = next(t for t in group_a["teams"] if t["bracket_contestant_id"] == self.teams[1].id)
        self.assertEqual(t2["average_position"], 2.0)
        t3 = next(t for t in group_a["teams"] if t["bracket_contestant_id"] == self.teams[2].id)
        self.assertEqual(t3["average_position"], 2.0)

        col_keys = [c["key"] for c in stats["knockout"]["columns"]]
        self.assertEqual(col_keys[-1], "group_winner")
        self.assertEqual(col_keys[0], "progression_score")
        row0 = next(
            r
            for r in stats["knockout"]["rows"]
            if r["bracket_contestant_id"] == self.teams[0].id
        )
        self.assertEqual(row0["percentages"]["group_winner"], 100.0)
        row1 = next(
            r
            for r in stats["knockout"]["rows"]
            if r["bracket_contestant_id"] == self.teams[1].id
        )
        self.assertEqual(row1["percentages"]["group_winner"], 0.0)

    def test_knockout_champion_percentage(self):
        ub1 = self._submit_with_groups(
            self.u1,
            {"A": {"1": self.teams[0].id, "2": self.teams[1].id, "3": self.teams[2].id, "4": self.teams[3].id},
             "B": {"1": self.teams[4].id, "2": self.teams[5].id, "3": self.teams[6].id, "4": self.teams[7].id}},
        )
        ub2 = self._submit_with_groups(
            self.u2,
            {"A": {"1": self.teams[0].id, "2": self.teams[1].id, "3": self.teams[2].id, "4": self.teams[3].id},
             "B": {"1": self.teams[4].id, "2": self.teams[5].id, "3": self.teams[6].id, "4": self.teams[7].id}},
        )
        final = KnockoutStage.objects.get(bracket=self.bracket, is_final=True)
        for ub in (ub1, ub2):
            fm = ub.matchup_set.get(stage=final, position=1)
            fm.contestant1 = self.teams[0]
            fm.contestant2 = self.teams[4]
            fm.winner = self.teams[0]
            fm.save()

        stats = compute_challenge_stats(self.challenge)
        champ_col = "champion"
        row0 = next(
            r
            for r in stats["knockout"]["rows"]
            if r["bracket_contestant_id"] == self.teams[0].id
        )
        self.assertEqual(row0["percentages"][champ_col], 100.0)
        row4 = next(
            r
            for r in stats["knockout"]["rows"]
            if r["bracket_contestant_id"] == self.teams[4].id
        )
        self.assertEqual(row4["percentages"][champ_col], 0.0)

    def test_knockout_runner_up_percentage(self):
        ub1 = self._submit_with_groups(
            self.u1,
            {"A": {"1": self.teams[0].id, "2": self.teams[1].id, "3": self.teams[2].id, "4": self.teams[3].id},
             "B": {"1": self.teams[4].id, "2": self.teams[5].id, "3": self.teams[6].id, "4": self.teams[7].id}},
        )
        ub2 = self._submit_with_groups(
            self.u2,
            {"A": {"1": self.teams[0].id, "2": self.teams[1].id, "3": self.teams[2].id, "4": self.teams[3].id},
             "B": {"1": self.teams[4].id, "2": self.teams[5].id, "3": self.teams[6].id, "4": self.teams[7].id}},
        )
        final = KnockoutStage.objects.get(bracket=self.bracket, is_final=True)
        for ub in (ub1, ub2):
            fm = ub.matchup_set.get(stage=final, position=1)
            fm.contestant1 = self.teams[0]
            fm.contestant2 = self.teams[4]
            fm.winner = self.teams[0]
            fm.save()

        stats = compute_challenge_stats(self.challenge)
        col_keys = [c["key"] for c in stats["knockout"]["columns"]]
        self.assertEqual(col_keys[0], "progression_score")
        self.assertEqual(col_keys[1], "champion")
        self.assertEqual(col_keys[2], "runner_up")

        row4 = next(
            r
            for r in stats["knockout"]["rows"]
            if r["bracket_contestant_id"] == self.teams[4].id
        )
        self.assertEqual(row4["percentages"]["runner_up"], 100.0)
        row0 = next(
            r
            for r in stats["knockout"]["rows"]
            if r["bracket_contestant_id"] == self.teams[0].id
        )
        self.assertEqual(row0["percentages"]["runner_up"], 0.0)

    def test_progression_score_prefers_deeper_advancement(self):
        ub1 = self._submit_with_groups(
            self.u1,
            {"A": {"1": self.teams[0].id, "2": self.teams[1].id, "3": self.teams[2].id, "4": self.teams[3].id},
             "B": {"1": self.teams[4].id, "2": self.teams[5].id, "3": self.teams[6].id, "4": self.teams[7].id}},
        )
        ub2 = self._submit_with_groups(
            self.u2,
            {"A": {"1": self.teams[0].id, "2": self.teams[1].id, "3": self.teams[2].id, "4": self.teams[3].id},
             "B": {"1": self.teams[4].id, "2": self.teams[5].id, "3": self.teams[6].id, "4": self.teams[7].id}},
        )
        semifinal = KnockoutStage.objects.get(bracket=self.bracket, number_of_contestants=4)
        for ub in (ub1, ub2):
            sm = ub.matchup_set.get(stage=semifinal, position=1)
            sm.contestant1 = self.teams[1]
            sm.contestant2 = self.teams[4]
            sm.save(update_fields=["contestant1", "contestant2"])

        stats = compute_challenge_stats(self.challenge)
        row_group_winner_only = next(
            r for r in stats["knockout"]["rows"] if r["bracket_contestant_id"] == self.teams[0].id
        )
        row_second_plus_advancement = next(
            r for r in stats["knockout"]["rows"] if r["bracket_contestant_id"] == self.teams[1].id
        )
        self.assertGreater(
            row_second_plus_advancement["progression_score"],
            row_group_winner_only["progression_score"],
        )

    def test_stats_api_requires_auth(self):
        res = self.client.get(f"/brackets/api/challenges/{self.challenge.id}/stats")
        self.assertEqual(res.status_code, 401)
