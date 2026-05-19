"""Tests for group-pick → knockout sync."""

from django.test import TestCase

from brackets.models import BracketContestant, Contestant, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.fwc26_regulations import (
    build_third_place_combinations_lookup,
    load_third_place_combinations_raw,
)
from brackets.utils.group_knockout_fill import MAPPING, apply_knockout_fill_to_stage
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell
from brackets.utils.sync_group_knockout import (
    parse_position_code,
    sync_first_knockout_from_group_picks,
    to_first_place_slot_code,
)


class ParsePositionCodeTests(TestCase):
    def test_a1_and_1a(self):
        self.assertEqual(parse_position_code("A1"), ("A", 1))
        self.assertEqual(parse_position_code("1A"), ("A", 1))

    def test_third_place(self):
        self.assertEqual(parse_position_code("3L"), ("L", 3))

    def test_winner_slot(self):
        self.assertEqual(to_first_place_slot_code("E1"), "1E")
        self.assertEqual(to_first_place_slot_code("2E"), None)


class SyncGroupKnockoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="picker", password="x")
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "groups-16-test",
            "Groups 16",
            16,
            self.user,
        )
        self.contestants: list[BracketContestant] = []
        for i in range(16):
            c = Contestant.objects.create(
                identifier=f"t{i}",
                name=f"Team {i}",
                created_by=self.user,
            )
            bc = BracketContestant.objects.create(
                bracket=self.bracket, contestant=c, seed=i + 1
            )
            self.contestants.append(bc)

        self.ub = self.bracket.userbracket_set.create(
            user=self.user,
            is_master=False,
        )
        ensure_knockout_matchup_shell(self.ub)

    def _group_bc_ids(self):
        """Preview order: 4 groups × 4 teams by seed."""
        return {
            "A": [self.contestants[i].id for i in range(0, 4)],
            "B": [self.contestants[i].id for i in range(4, 8)],
            "C": [self.contestants[i].id for i in range(8, 12)],
            "D": [self.contestants[i].id for i in range(12, 16)],
        }

    def test_standard_group_knockout_fills_r16(self):
        g = self._group_bc_ids()
        self.ub.metadata = {
            "group_positions": {
                "A": {"1": g["A"][0], "2": g["A"][1]},
                "B": {"1": g["B"][0], "2": g["B"][1]},
                "C": {"1": g["C"][0], "2": g["C"][1]},
                "D": {"1": g["D"][0], "2": g["D"][1]},
            }
        }
        self.ub.save()

        n = sync_first_knockout_from_group_picks(self.ub)
        self.assertGreaterEqual(n, 1)

        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        m1 = Matchup.objects.get(
            user_bracket=self.ub, stage=first_ko, position=1
        )
        self.assertEqual(m1.contestant1_id, g["A"][0])
        self.assertEqual(m1.contestant2_id, g["B"][1])


class SyncWorldCupKnockoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="wc", password="x")
        combinations = build_third_place_combinations_lookup(
            load_third_place_combinations_raw()
        )
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "wc-mini-test",
            "WC mini",
            48,
            self.user,
        )
        self.bracket.metadata = {
            "tournament_type": "world_cup_2026",
            "third_place_combinations": combinations,
        }
        self.bracket.save()

        self.contestants = []
        for i in range(48):
            c = Contestant.objects.create(
                identifier=f"wc{i}",
                name=f"WC {i}",
                created_by=self.user,
            )
            self.contestants.append(
                BracketContestant.objects.create(
                    bracket=self.bracket, contestant=c, seed=i + 1
                )
            )

        from brackets.models import KnockoutStage

        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        apply_knockout_fill_to_stage(
            KnockoutStage.objects.get(pk=first_ko.pk),
            [(1, "E1", "3E"), (7, "A1", "3A")],
            method=MAPPING,
        )

        self.ub = self.bracket.userbracket_set.create(
            user=self.user,
            is_master=False,
        )
        ensure_knockout_matchup_shell(self.ub)

    def _bc_for_group_slot(self, group_index: int, slot_in_group: int) -> int:
        per = 4
        base = group_index * per
        return self.contestants[base + slot_in_group].id

    def test_wc_third_place_pairing_resolves_opponent(self):
        """E1 vs third-place uses FIFA combination, not literal 3E in template."""
        from brackets.utils.sync_group_knockout import (
            _placement_map,
            _third_place_group_codes,
            _wc_third_place_pairings,
        )

        e1 = self._bc_for_group_slot(4, 0)  # group E, first
        e3 = self._bc_for_group_slot(4, 2)
        a1 = self._bc_for_group_slot(0, 0)

        gp = {}
        for i, letter in enumerate("ABCDEFGHIJKL"):
            gp[letter] = {
                "1": self._bc_for_group_slot(i, 0),
                "2": self._bc_for_group_slot(i, 1),
                "3": self._bc_for_group_slot(i, 2),
            }

        # Eight third-place teams (regulation option 1 from fwc26 tests)
        third_letters = ["E", "J", "I", "F", "H", "G", "L", "K"]
        third_advancers = [gp[L]["3"] for L in third_letters]

        metadata = {
            "group_positions": gp,
            "third_place_advancers": third_advancers,
        }
        self.ub.metadata = metadata
        self.ub.save()

        sync_first_knockout_from_group_picks(self.ub)

        placements = _placement_map(self.bracket, metadata)
        third_codes = _third_place_group_codes(metadata, placements)
        pairings = _wc_third_place_pairings(self.bracket, third_codes)
        self.assertIsNotNone(pairings)
        paired_group = pairings["1E"][1]
        expected_e_opponent = gp[paired_group]["3"]

        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        m_e = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=1)
        self.assertEqual(m_e.contestant1_id, e1)
        self.assertEqual(m_e.contestant2_id, expected_e_opponent)
        self.assertNotEqual(m_e.contestant2_id, e3)

        paired_a_group = pairings["1A"][1]
        expected_a_opponent = gp[paired_a_group]["3"]
        m_a = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=7)
        self.assertEqual(m_a.contestant1_id, a1)
        self.assertEqual(m_a.contestant2_id, expected_a_opponent)
