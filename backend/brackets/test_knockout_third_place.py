"""Third-place knockout stage: semifinal losers feed the bronze match."""

from django.test import TestCase

from brackets.models import Bracket, KnockoutStage, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
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
