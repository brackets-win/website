"""Third-place knockout stage: semifinal losers feed the bronze match."""

from django.test import TestCase

from brackets.models import BracketContestant, KnockoutStage, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_rebuild import clear_matchup_winner_and_downstream
from brackets.utils.knockout_tree import (
    ensure_knockout_matchup_shell,
    ensure_third_place_matchup_wired,
)


class KnockoutThirdPlaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ko3", password="x")
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "wc-style-16",
            "WC style 16",
            16,
            self.user,
            has_third_place=True,
        )
        # Create contestants so tests can assign them to matchups
        for i in range(16):
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i+1}", seed=i + 1
            )
        self.ub = self.bracket.get_master_bracket()
        ensure_knockout_matchup_shell(self.ub)

    def test_group_knockout_has_third_place_stage(self):
        self.assertTrue(self.bracket.has_third_place_match)
        tp = KnockoutStage.objects.filter(
            bracket=self.bracket, is_third_place=True
        ).first()
        self.assertIsNotNone(tp)
        self.assertEqual(tp.name, "Third place")

    def test_third_place_matchup_sources_semifinal_losers(self):
        tp_stage = KnockoutStage.objects.get(bracket=self.bracket, is_third_place=True)
        m = ensure_third_place_matchup_wired(self.ub, tp_stage)
        self.assertFalse(m.source_a_uses_winner)
        self.assertFalse(m.source_b_uses_winner)
        self.assertIsNotNone(m.source_a_matchup_id)
        self.assertIsNotNone(m.source_b_matchup_id)
        sf = KnockoutStage.objects.get(bracket=self.bracket, number_of_contestants=4)
        sf_ids = set(
            Matchup.objects.filter(user_bracket=self.ub, stage=sf).values_list(
                "id", flat=True
            )
        )
        self.assertIn(m.source_a_matchup_id, sf_ids)
        self.assertIn(m.source_b_matchup_id, sf_ids)

    def test_clearing_semifinal_clears_third_place_loser_slot(self):
        tp_stage = KnockoutStage.objects.get(bracket=self.bracket, is_third_place=True)
        tp = ensure_third_place_matchup_wired(self.ub, tp_stage)
        sf = KnockoutStage.objects.get(bracket=self.bracket, number_of_contestants=4)
        sf1 = Matchup.objects.get(user_bracket=self.ub, stage=sf, position=1)
        teams = list(
            BracketContestant.objects.filter(bracket=self.bracket).order_by("seed")[
                :4
            ]
        )
        sf1.contestant1 = teams[0]
        sf1.contestant2 = teams[1]
        sf1.winner = teams[0]
        sf1.save()

        tp.refresh_from_db()
        self.assertEqual(tp.contestant1_id, teams[1].id)

        clear_matchup_winner_and_downstream(sf1)

        tp.refresh_from_db()
        sf1.refresh_from_db()
        self.assertIsNone(sf1.winner_id)
        self.assertIsNone(tp.contestant1_id)
        self.assertIsNone(tp.winner_id)

    def test_semifinal_winner_fills_final_when_third_place_wired(self):
        """Third-place loser feeds must not block semi winners advancing to the final."""
        tp_stage = KnockoutStage.objects.get(bracket=self.bracket, is_third_place=True)
        ensure_third_place_matchup_wired(self.ub, tp_stage)
        sf = KnockoutStage.objects.get(bracket=self.bracket, number_of_contestants=4)
        final = KnockoutStage.objects.get(bracket=self.bracket, is_final=True)
        sf1 = Matchup.objects.get(user_bracket=self.ub, stage=sf, position=1)
        sf2 = Matchup.objects.get(user_bracket=self.ub, stage=sf, position=2)
        final_m = Matchup.objects.get(user_bracket=self.ub, stage=final, position=1)
        teams = list(
            BracketContestant.objects.filter(bracket=self.bracket).order_by("seed")[
                :4
            ]
        )
        for i, m in enumerate([sf1, sf2], start=0):
            m.contestant1 = teams[i * 2]
            m.contestant2 = teams[i * 2 + 1]
            m.winner = teams[i * 2]
            m.save()

        final_m.refresh_from_db()
        self.assertEqual(final_m.contestant1_id, teams[0].id)
        self.assertEqual(final_m.contestant2_id, teams[2].id)
