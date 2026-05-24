import unittest

from brackets.data.fwc26.r32_tree_slots import R32_TREE_SLOTS, build_r32_group_knockout_mapping
from brackets.utils.bracket_seeding import bracket_seed_order, first_round_seed_pairs
from brackets.utils.fwc26_regulations import (
    build_third_place_combinations_lookup,
    load_third_place_combinations_raw,
    teams_to_bit_vector,
)


class BracketSeedingTests(unittest.TestCase):
    def test_32_team_first_round_pairs(self):
        pairs = first_round_seed_pairs(32)
        self.assertEqual(len(pairs), 16)
        self.assertEqual(pairs[0], (1, 32))
        self.assertEqual(pairs[1], (16, 17))
        self.assertEqual(pairs[2], (8, 25))

    def test_8_team_bracket_order(self):
        self.assertEqual(bracket_seed_order(8), [1, 8, 4, 5, 2, 7, 3, 6])


class Fwc26RegulationsTests(unittest.TestCase):
    def test_third_place_table_row_count(self):
        raw = load_third_place_combinations_raw()
        lookup = build_third_place_combinations_lookup(raw)
        self.assertEqual(len(lookup), 495)

    def test_third_place_option_one_bit_vector(self):
        raw = load_third_place_combinations_raw()
        lookup = build_third_place_combinations_lookup(raw)
        teams = ["3E", "3J", "3I", "3F", "3H", "3G", "3L", "3K"]
        key = str(teams_to_bit_vector(teams))
        self.assertEqual(lookup[key]["option"], "1")
        self.assertEqual(lookup[key]["teams"], teams)

    def test_r32_tree_slots(self):
        self.assertEqual(len(R32_TREE_SLOTS), 16)
        self.assertEqual(len(build_r32_group_knockout_mapping()), 16)
        by_pos = {pos: (a, b) for pos, a, b in R32_TREE_SLOTS}
        # M101 half (same side as 1I): 2A/2B, 1I, 2K/2L
        self.assertEqual(by_pos[2][0], "I1")
        self.assertEqual(by_pos[3], ("A2", "B2"))
        self.assertEqual(by_pos[5], ("K2", "L2"))
        # M102 half: 1L
        self.assertEqual(by_pos[12][0], "L1")
