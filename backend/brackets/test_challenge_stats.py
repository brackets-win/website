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
        self.assertEqual(t2["average_position"], 2.5)
        t3 = next(t for t in group_a["teams"] if t["bracket_contestant_id"] == self.teams[2].id)
        self.assertEqual(t3["average_position"], 2.5)

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

    def test_bracket_slot_distribution(self):
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
        # u1 picks T1 champion, u2 picks T5 champion (same finalists).
        for ub, winner in ((ub1, self.teams[0]), (ub2, self.teams[4])):
            fm = ub.matchup_set.get(stage=final, position=1)
            fm.contestant1 = self.teams[0]
            fm.contestant2 = self.teams[4]
            fm.winner = winner
            fm.save()

        stats = compute_challenge_stats(self.challenge)
        slots = stats["bracket"]["slots"]

        # Both placed T1/T5 into the final's two slots.
        top_slot = slots[f"{final.id}:1:1"]
        self.assertEqual(top_slot[0]["bracket_contestant_id"], self.teams[0].id)
        self.assertEqual(top_slot[0]["pct"], 100.0)
        bot_slot = slots[f"{final.id}:1:2"]
        self.assertEqual(bot_slot[0]["bracket_contestant_id"], self.teams[4].id)
        self.assertEqual(bot_slot[0]["pct"], 100.0)

        # Champion split 50/50 between the two finalists, most common first.
        champ = slots["champion"]
        self.assertEqual({e["bracket_contestant_id"] for e in champ},
                         {self.teams[0].id, self.teams[4].id})
        self.assertEqual([e["pct"] for e in champ], [50.0, 50.0])

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
        final = KnockoutStage.objects.get(bracket=self.bracket, is_final=True)
        for ub in (ub1, ub2):
            fm = ub.matchup_set.get(stage=final, position=1)
            fm.contestant1 = self.teams[1]
            fm.contestant2 = self.teams[4]
            fm.save(update_fields=["contestant1", "contestant2"])

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

    def test_group_points_breakdown(self):
        t = [team.id for team in self.teams]
        master = self.bracket.get_master_bracket()
        master.metadata = {
            "group_positions": {
                "A": {"1": t[0], "2": t[1], "3": t[2], "4": t[3]},
                "B": {"1": t[4], "2": t[5], "3": t[6], "4": t[7]},
            }
        }
        master.save(update_fields=["metadata"])

        # u1 matches the master exactly in group A.
        self._submit_with_groups(
            self.u1,
            {
                "A": {"1": t[0], "2": t[1], "3": t[2], "4": t[3]},
                "B": {"1": t[4], "2": t[5], "3": t[6], "4": t[7]},
            },
        )
        # u2 swaps the non-qualifying 3rd/4th spots in group A: loses 2 exact
        # placement points but still gets the same qualifiers into the knockout.
        self._submit_with_groups(
            self.u2,
            {
                "A": {"1": t[0], "2": t[1], "3": t[3], "4": t[2]},
                "B": {"1": t[4], "2": t[5], "3": t[6], "4": t[7]},
            },
        )

        stats = compute_challenge_stats(self.challenge)
        group_a = next(g for g in stats["group_stage"] if g["code"] == "A")

        # 4 exact placements + 2 qualifiers into the first knockout round.
        self.assertEqual(group_a["max_points"], 6)
        self.assertEqual(group_a["avg_points"], 5.0)

        points_by_name = {
            e["display_name"]: e["points"] for e in group_a["entries"]
        }
        self.assertEqual(points_by_name["u1"], 6)
        self.assertEqual(points_by_name["u2"], 4)
        # Ordered by points desc, then entry name.
        self.assertEqual(group_a["entries"][0]["display_name"], "u1")
        self.assertEqual(group_a["entries"][1]["display_name"], "u2")

    def test_knockout_progression_buckets(self):
        t = [team.id for team in self.teams]
        ub1 = self._submit_with_groups(
            self.u1,
            {
                "A": {"1": t[0], "2": t[1], "3": t[2], "4": t[3]},
                "B": {"1": t[4], "2": t[5], "3": t[6], "4": t[7]},
            },
        )
        ub2 = self._submit_with_groups(
            self.u2,
            {
                "A": {"1": t[0], "2": t[1], "3": t[3], "4": t[2]},
                "B": {"1": t[4], "2": t[5], "3": t[6], "4": t[7]},
            },
        )
        final = KnockoutStage.objects.get(bracket=self.bracket, is_final=True)
        # u1 makes T1 champion; u2 makes T1 runner-up (reaches the final).
        fm1 = ub1.matchup_set.get(stage=final, position=1)
        fm1.contestant1 = self.teams[0]
        fm1.contestant2 = self.teams[4]
        fm1.winner = self.teams[0]
        fm1.save()
        fm2 = ub2.matchup_set.get(stage=final, position=1)
        fm2.contestant1 = self.teams[0]
        fm2.contestant2 = self.teams[4]
        fm2.winner = self.teams[4]
        fm2.save()

        stats = compute_challenge_stats(self.challenge)
        row_t1 = next(
            r
            for r in stats["knockout"]["rows"]
            if r["bracket_contestant_id"] == t[0]
        )
        prog = row_t1["progression"]
        labels = [b["label"] for b in prog]
        # No third-place match here: Champions, then Runner-Up (not "Final").
        self.assertEqual(labels[0], "Champions")
        self.assertIn("Runner-Up", labels)
        self.assertNotIn("Final", labels)
        self.assertLess(labels.index("Champions"), labels.index("Runner-Up"))
        champ_names = [
            e["display_name"] for e in prog[0]["entries"]
        ]
        self.assertEqual(champ_names, ["u1"])
        runner_up_names = [
            e["display_name"]
            for b in prog
            if b["label"] == "Runner-Up"
            for e in b["entries"]
        ]
        self.assertEqual(runner_up_names, ["u2"])

        # T3 was placed 3rd/4th in group A (never advanced) by both entries.
        row_t3 = next(
            r
            for r in stats["knockout"]["rows"]
            if r["bracket_contestant_id"] == t[2]
        )
        t3_labels = [b["label"] for b in row_t3["progression"]]
        self.assertTrue(
            all("in Group" in lbl for lbl in t3_labels),
            t3_labels,
        )
        # Every bucket has at least one entry.
        for bucket in row_t3["progression"]:
            self.assertGreaterEqual(len(bucket["entries"]), 1)

    def test_knockout_progression_third_place_buckets(self):
        from django.utils import timezone

        host = User.objects.create_user(username="tp_host", password="x")
        u1 = User.objects.create_user(username="tp1", password="x")
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "stats-tp", "Stats TP", 8, host, has_third_place=True
        )
        teams = [
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(8)
        ]
        challenge = BracketChallenge.objects.create(
            name="Pool TP", bracket=bracket, created_by=host
        )
        ub = UserBracket.objects.create(
            bracket=bracket,
            user=u1,
            challenge=challenge,
            is_master=False,
            metadata={
                "group_positions": {
                    "A": {
                        "1": teams[0].id,
                        "2": teams[1].id,
                        "3": teams[2].id,
                        "4": teams[3].id,
                    },
                    "B": {
                        "1": teams[4].id,
                        "2": teams[5].id,
                        "3": teams[6].id,
                        "4": teams[7].id,
                    },
                }
            },
        )
        ub.submitted_at = timezone.now()
        ub.save(update_fields=["submitted_at", "metadata"])
        ensure_knockout_matchup_shell(ub)

        final = KnockoutStage.objects.get(bracket=bracket, is_final=True)
        third = KnockoutStage.objects.get(bracket=bracket, is_third_place=True)
        # T1 champion, T5 runner-up; T2 third place, T6 fourth place.
        fm = ub.matchup_set.filter(stage=final).first()
        fm.contestant1 = teams[0]
        fm.contestant2 = teams[4]
        fm.winner = teams[0]
        fm.save()
        tp = ub.matchup_set.filter(stage=third).first()
        tp.contestant1 = teams[1]
        tp.contestant2 = teams[5]
        tp.winner = teams[1]
        tp.save()

        stats = compute_challenge_stats(challenge)
        rows = {
            r["bracket_contestant_id"]: r for r in stats["knockout"]["rows"]
        }

        self.assertEqual(rows[teams[0].id]["progression"][0]["label"], "Champions")
        self.assertEqual(rows[teams[4].id]["progression"][0]["label"], "Runner-Up")

        t2_labels = [b["label"] for b in rows[teams[1].id]["progression"]]
        self.assertIn("Third Place", t2_labels)
        self.assertNotIn("Semi Final", t2_labels)

        t6_labels = [b["label"] for b in rows[teams[5].id]["progression"]]
        self.assertIn("Fourth Place", t6_labels)
        self.assertNotIn("Semi Final", t6_labels)

    def test_stats_api_requires_auth(self):
        res = self.client.get(f"/brackets/api/challenges/{self.challenge.id}/stats")
        self.assertEqual(res.status_code, 401)
