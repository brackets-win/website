"""Bracket.has_third_place_match drives third-place stage + matchup wiring."""

from django.test import TestCase

from brackets.models import KnockoutStage, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell
from brackets.utils.third_place_structure import sync_third_place_structure


class ThirdPlaceStructureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tp", password="x")

    def test_enable_creates_stage_and_wires_master(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "tp-on",
            "TP on",
            16,
            self.user,
            has_third_place=True,
        )
        ub = bracket.get_master_bracket()
        ensure_knockout_matchup_shell(ub)

        tp = KnockoutStage.objects.get(bracket=bracket, is_third_place=True)
        m = Matchup.objects.get(user_bracket=ub, stage=tp)
        self.assertFalse(m.source_a_uses_winner)
        self.assertFalse(m.source_b_uses_winner)

    def test_disable_removes_stage(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "tp-off",
            "TP off",
            16,
            self.user,
            has_third_place=True,
        )
        bracket.has_third_place_match = False
        bracket.save(update_fields=["has_third_place_match"])
        sync_third_place_structure(bracket)

        self.assertFalse(
            KnockoutStage.objects.filter(bracket=bracket, is_third_place=True).exists()
        )

    def test_single_elim_third_place_at_create_does_not_raise(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "tp-se-16",
            "TP SE 16",
            16,
            self.user,
            has_third_place=True,
        )
        self.assertTrue(
            KnockoutStage.objects.filter(bracket=bracket, is_third_place=True).exists()
        )

    def test_enable_on_existing_bracket_wires_master(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "tp-existing",
            "TP existing",
            16,
            self.user,
            has_third_place=False,
        )
        ub = bracket.get_master_bracket()
        ensure_knockout_matchup_shell(ub)

        bracket.has_third_place_match = True
        bracket.save(update_fields=["has_third_place_match"])
        sync_third_place_structure(bracket)

        tp = KnockoutStage.objects.get(bracket=bracket, is_third_place=True)
        self.assertTrue(Matchup.objects.filter(user_bracket=ub, stage=tp).exists())
