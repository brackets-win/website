"""Bracket similarity clusters by shared top-eight knockout picks."""

from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketChallenge, BracketContestant, KnockoutStage, User, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.bracket_similarity import build_bracket_similarity_tree
from brackets.utils.challenge_stats import compute_challenge_stats
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell


class BracketSimilarityTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.u1 = User.objects.create_user(username="alice", password="x")
        self.u2 = User.objects.create_user(username="bob", password="x")
        self.u3 = User.objects.create_user(username="carol", password="x")

    def _teams(self, bracket, n: int):
        return [
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(n)
        ]

    def _submit(self, challenge, user, teams, picks):
        ub = UserBracket.objects.create(
            bracket=challenge.bracket,
            user=user,
            challenge=challenge,
            is_master=False,
            display_name=user.username,
        )
        ensure_knockout_matchup_shell(ub)
        qf, sf, final = self._ko_stages(challenge.bracket)

        for stage, matchups in picks.items():
            for position, (c1, c2, winner) in enumerate(matchups, start=1):
                m = ub.matchup_set.get(stage=stage, position=position)
                m.contestant1 = teams[c1]
                m.contestant2 = teams[c2]
                m.winner = teams[winner]
                m.save()

        ub.submitted_at = timezone.now()
        ub.save(update_fields=["submitted_at"])
        return ub

    def _ko_stages(self, bracket):
        qf = KnockoutStage.objects.get(bracket=bracket, number_of_contestants=8)
        sf = KnockoutStage.objects.get(bracket=bracket, number_of_contestants=4)
        final = KnockoutStage.objects.get(bracket=bracket, is_final=True)
        return qf, sf, final

    def test_clusters_identical_top_eight(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "sim8", "Sim8", 8, self.host
        )
        teams = self._teams(bracket, 8)
        challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=bracket,
            created_by=self.host,
        )

        shared = {
            "qf": [
                (0, 1, 0),
                (2, 3, 2),
                (4, 5, 4),
                (6, 7, 6),
            ],
            "sf": [
                (0, 2, 0),
                (4, 6, 4),
            ],
            "final": [
                (0, 4, 0),
            ],
        }
        qf, sf, final = self._ko_stages(bracket)
        ub1 = self._submit(
            challenge,
            self.u1,
            teams,
            {qf: shared["qf"], sf: shared["sf"], final: shared["final"]},
        )
        ub2 = self._submit(
            challenge,
            self.u2,
            teams,
            {qf: shared["qf"], sf: shared["sf"], final: shared["final"]},
        )
        self._submit(
            challenge,
            self.u3,
            teams,
            {
                qf: shared["qf"],
                sf: shared["sf"],
                final: [(0, 4, 4)],
            },
        )

        stats = compute_challenge_stats(challenge)
        similarity = stats["similarity"]
        self.assertIsNotNone(similarity)
        self.assertFalse(similarity["has_third_place"])
        tree = similarity["tree"]
        self.assertEqual(len(tree), 2)
        champ_t1 = next(n for n in tree if n["team"]["display_name"] == "T1")
        champ_t5 = next(n for n in tree if n["team"]["display_name"] == "T5")
        self.assertEqual(champ_t1["count"], 2)
        self.assertEqual(champ_t5["count"], 1)
        leaf = (
            champ_t1["children"][0]["children"][0]["children"][0]["children"][0]
        )
        entry_ids = {e["user_bracket_id"] for e in leaf["entries"]}
        self.assertEqual(entry_ids, {ub1.id, ub2.id})

    def test_quarter_finalists_sorted_alphabetically(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "sim8b", "Sim8b", 8, self.host
        )
        teams = self._teams(bracket, 8)
        qf, sf, final = self._ko_stages(bracket)
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.u1, is_master=False
        )
        ensure_knockout_matchup_shell(ub)

        contestant_info = {
            teams[i].id: {"display_name": teams[i].name_override, "image_url": None}
            for i in range(8)
        }
        for position, (c1, c2, winner) in enumerate(
            [
                (0, 1, 0),
                (2, 3, 2),
                (4, 5, 4),
                (6, 7, 6),
            ],
            start=1,
        ):
            m = ub.matchup_set.get(stage=qf, position=position)
            m.contestant1, m.contestant2, m.winner = (
                teams[c1],
                teams[c2],
                teams[winner],
            )
            m.save()
        for position, (c1, c2, winner) in enumerate([(0, 2, 0), (4, 6, 4)], start=1):
            m = ub.matchup_set.get(stage=sf, position=position)
            m.contestant1, m.contestant2, m.winner = (
                teams[c1],
                teams[c2],
                teams[winner],
            )
            m.save()
        final_m = ub.matchup_set.get(stage=final, position=1)
        final_m.contestant1, final_m.contestant2, final_m.winner = (
            teams[0],
            teams[4],
            teams[0],
        )
        final_m.save()

        main_ko = list(
            bracket.stages.filter(stage_type="KNOCKOUT").order_by("order")
        )
        result = build_bracket_similarity_tree(
            [ub],
            bracket=bracket,
            main_knockout_stages=main_ko,
            contestant_info=contestant_info,
        )
        self.assertIsNotNone(result)
        leaf = result["tree"][0]["children"][0]["children"][0]["children"][0]["children"][0]
        qf_names = [t["display_name"] for t in leaf["quarter_finalists"]]
        self.assertEqual(qf_names, ["T2", "T4", "T6", "T8"])
