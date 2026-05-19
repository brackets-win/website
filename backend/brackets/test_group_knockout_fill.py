"""Tests for group → knockout fill methods."""

from django.test import TestCase

from brackets.data.fwc26.r32_tree_slots import (
    FINISHER_TO_BRACKET_SEED,
    build_r32_group_knockout_mapping,
)
from brackets.utils.bracket_seeding import first_round_seed_pairs
from brackets.utils.group_knockout_fill import (
    MAPPING,
    SEEDING,
    STANDARD,
    get_knockout_fill_method,
    load_knockout_mapping,
)


class _Stage:
    def __init__(self, metadata=None, order=10):
        self.metadata = metadata
        self.order = order


class _Bracket:
    def __init__(self, metadata=None):
        self.metadata = metadata

    def stages(self):
        return _StagesQuery()


class _StagesQuery:
    def filter(self, **kwargs):
        return self

    def order_by(self, *_):
        return self

    def first(self):
        return None


class KnockoutFillMethodTests(TestCase):
    def test_default_is_standard(self):
        self.assertEqual(get_knockout_fill_method(_Stage()), STANDARD)

    def test_invalid_method_falls_back(self):
        self.assertEqual(
            get_knockout_fill_method(
                _Stage(metadata={"knockout_fill_method": "custom"})
            ),
            STANDARD,
        )


class KnockoutMappingLoadTests(TestCase):
    def test_standard_four_groups(self):
        stage = _Stage(metadata={"knockout_fill_method": STANDARD})
        bracket = _Bracket()
        mapping = load_knockout_mapping(
            bracket, stage, num_groups=4
        )
        self.assertEqual(mapping[0], (1, "A1", "B2"))

    def test_seeding_eight_groups(self):
        stage = _Stage(metadata={"knockout_fill_method": SEEDING})
        bracket = _Bracket()
        mapping = load_knockout_mapping(
            bracket, stage, num_groups=8
        )
        pairs = first_round_seed_pairs(16)
        self.assertEqual(len(mapping), len(pairs))
        self.assertEqual(mapping[0][1], "A1")

    def test_mapping_from_metadata(self):
        stage = _Stage(
            metadata={
                "knockout_fill_method": MAPPING,
                "group_knockout_mapping": {
                    "1": {"team_a": "E1", "team_b": "3E"},
                },
            }
        )
        bracket = _Bracket()
        self.assertEqual(
            load_knockout_mapping(bracket, stage),
            [(1, "E1", "3E")],
        )

    def test_wc26_default_mapping(self):
        stage = _Stage(metadata={"knockout_fill_method": MAPPING})
        bracket = _Bracket(metadata={"tournament_type": "world_cup_2026"})
        mapping = load_knockout_mapping(bracket, stage)
        self.assertEqual(mapping, build_r32_group_knockout_mapping())


class Fwc26BracketHalfTests(TestCase):
    def test_i1_and_l1_on_opposite_tree_halves(self):
        """M101 (pos 1–8) vs M102 (pos 9–16) — mirror left/right columns."""
        mapping = build_r32_group_knockout_mapping()
        i_pos = next(
            p for p, a, b in mapping if a == "I1" or b == "I1"
        )
        l_pos = next(
            p for p, a, b in mapping if a == "L1" or b == "L1"
        )
        self.assertLessEqual(i_pos, 8)
        self.assertGreater(l_pos, 8)

    def test_i1_and_l1_bracket_seeds(self):
        self.assertEqual(FINISHER_TO_BRACKET_SEED["I1"], 16)
        self.assertEqual(FINISHER_TO_BRACKET_SEED["L1"], 10)
