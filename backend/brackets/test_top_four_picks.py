"""Top-four leaderboard picks: champion, runner-up, bronze or semi losers."""

from django.test import TestCase

from brackets.models import BracketContestant, KnockoutStage, User, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell, ensure_third_place_matchup_wired
from brackets.utils.top_four_picks import serialize_top_four_picks, top_four_bracket_contestants


class TopFourPicksTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="top4", password="x")

    def _teams(self, bracket, n: int):
        return [
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(n)
        ]

    def test_four_team_single_elim_semifinal_losers(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "se4", "SE4", 4, self.user
        )
        teams = self._teams(bracket, 4)
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        ensure_knockout_matchup_shell(ub)

        semi = KnockoutStage.objects.get(bracket=bracket, number_of_contestants=4)
        final = KnockoutStage.objects.get(bracket=bracket, is_final=True)
        sf1 = ub.matchup_set.get(stage=semi, position=1)
        sf2 = ub.matchup_set.get(stage=semi, position=2)
        final_m = ub.matchup_set.get(stage=final, position=1)

        sf1.contestant1, sf1.contestant2, sf1.winner = teams[0], teams[1], teams[0]
        sf1.save()
        sf2.contestant1, sf2.contestant2, sf2.winner = teams[2], teams[3], teams[2]
        sf2.save()
        final_m.contestant1, final_m.contestant2, final_m.winner = (
            teams[0],
            teams[2],
            teams[0],
        )
        final_m.save()

        picks = top_four_bracket_contestants(ub)
        self.assertEqual(picks[0], teams[0])
        self.assertEqual(picks[1], teams[2])
        self.assertEqual(picks[2], teams[1])
        self.assertEqual(picks[3], teams[3])

        serialized = serialize_top_four_picks(ub)
        self.assertEqual(len(serialized), 4)
        self.assertEqual(serialized[0]["display_name"], "T1")
        self.assertEqual(serialized[2]["display_name"], "T2")

    def test_third_place_match_picks(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "gk16",
            "GK16",
            16,
            self.user,
            has_third_place=True,
        )
        teams = self._teams(bracket, 8)
        ub = bracket.get_master_bracket()
        ensure_knockout_matchup_shell(ub)

        sf = KnockoutStage.objects.get(bracket=bracket, number_of_contestants=4)
        final = KnockoutStage.objects.get(bracket=bracket, is_final=True)
        tp = KnockoutStage.objects.get(bracket=bracket, is_third_place=True)
        ensure_third_place_matchup_wired(ub, tp)

        sf1 = ub.matchup_set.get(stage=sf, position=1)
        sf2 = ub.matchup_set.get(stage=sf, position=2)
        final_m = ub.matchup_set.get(stage=final, position=1)
        tp_m = ub.matchup_set.get(stage=tp, position=1)

        sf1.contestant1, sf1.contestant2, sf1.winner = teams[0], teams[1], teams[0]
        sf1.save()
        sf2.contestant1, sf2.contestant2, sf2.winner = teams[2], teams[3], teams[2]
        sf2.save()
        final_m.contestant1, final_m.contestant2, final_m.winner = (
            teams[0],
            teams[2],
            teams[0],
        )
        final_m.save()
        tp_m.contestant1, tp_m.contestant2, tp_m.winner = teams[1], teams[3], teams[1]
        tp_m.save()

        picks = top_four_bracket_contestants(ub)
        self.assertEqual(picks, [teams[0], teams[2], teams[1], teams[3]])
