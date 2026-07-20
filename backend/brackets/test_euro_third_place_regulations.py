"""
Euro 2024 third-place knockout seeding must use ``third_place_combinations.txt``
via a bit-vector lookup — not random assignment or literal ``3X`` template codes.
"""

from django.test import TestCase

from brackets.data.euro24.r16_tree_slots import (
    R16_TREE_SLOTS,
    build_r16_group_knockout_mapping,
)
from brackets.models import BracketContestant, Contestant, KnockoutStage, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.bracket_seeding import first_round_seed_pairs
from brackets.utils.euro24_regulations import (
    build_third_place_combinations_lookup,
    load_third_place_combinations_raw,
    teams_to_bit_vector,
)
from brackets.utils.group_knockout_fill import MAPPING, apply_knockout_fill_to_stage
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell
from brackets.utils.sync_group_knockout import (
    _placement_map,
    _third_place_group_codes,
    _wc_third_place_pairings,
    sync_first_knockout_from_group_picks,
)


def _regulation_lookup() -> dict:
    return build_third_place_combinations_lookup(load_third_place_combinations_raw())


class Euro24ThirdPlaceRegulationLookupTests(TestCase):
    """Lookup table shape and determinism (file → bracket.metadata)."""

    def test_lookup_has_15_regulation_rows(self):
        self.assertEqual(len(_regulation_lookup()), 15)

    def test_cdef_matches_actual_euro_2024_assignment(self):
        """Real Euro 2024: thirds from C,D,E,F → 1B=3F, 1C=3E, 1E=3D, 1F=3C."""
        teams = ["3C", "3D", "3E", "3F"]
        lookup = _regulation_lookup()
        row = lookup[str(teams_to_bit_vector(teams))]
        self.assertEqual(row["option"], "CDEF")
        self.assertEqual(
            row["matchups"],
            {"1B": "3F", "1C": "3E", "1E": "3D", "1F": "3C"},
        )

    def test_abcd_matches_excel_challenge(self):
        """Historical Excel: ABCD → F1 gets B3, E1 gets C3 (UEFA swaps those)."""
        teams = ["3A", "3B", "3C", "3D"]
        lookup = _regulation_lookup()
        row = lookup[str(teams_to_bit_vector(teams))]
        self.assertEqual(row["option"], "ABCD")
        self.assertEqual(
            row["matchups"],
            {"1B": "3A", "1C": "3D", "1E": "3C", "1F": "3B"},
        )

    def test_same_four_groups_always_same_bit_vector_key(self):
        teams = ["3C", "3D", "3E", "3F"]
        k1 = str(teams_to_bit_vector(teams))
        k2 = str(teams_to_bit_vector(list(reversed(teams))))
        self.assertEqual(k1, k2)

    def test_pairings_returns_exact_matchups_dict_from_lookup(self):
        lookup = _regulation_lookup()
        third_codes = ["3C", "3D", "3E", "3F"]
        key = str(teams_to_bit_vector(third_codes))
        expected = lookup[key]["matchups"]

        bracket = type(
            "B",
            (),
            {
                "metadata": {
                    "tournament_type": "euro_2024",
                    "third_place_combinations": lookup,
                }
            },
        )()
        pairings = _wc_third_place_pairings(bracket, third_codes)
        self.assertEqual(pairings, expected)


class Euro24R16TreeSlotTests(TestCase):
    def test_eight_slots_match_seed_pair_order(self):
        pairs = first_round_seed_pairs(16)
        self.assertEqual(len(R16_TREE_SLOTS), 8)
        self.assertEqual(
            [pairs[pos - 1] for pos, _, _ in R16_TREE_SLOTS],
            [(1, 16), (8, 9), (4, 13), (5, 12), (2, 15), (7, 10), (3, 14), (6, 11)],
        )

    def test_mapping_codes_match_user_r16_order(self):
        mapping = build_r16_group_knockout_mapping()
        self.assertEqual(
            mapping,
            [
                (1, "A1", "C2"),
                (2, "B1", "3B"),
                (3, "F1", "3F"),
                (4, "D2", "E2"),
                (5, "D1", "F2"),
                (6, "E1", "3E"),
                (7, "C1", "3C"),
                (8, "A2", "B2"),
            ],
        )


class Euro24ThirdPlaceKnockoutSyncTests(TestCase):
    """End-to-end: user picks → bit vector → regulation row → R16 contestants."""

    def setUp(self):
        self.user = User.objects.create_user(username="euro-reg", password="x")
        self.lookup = _regulation_lookup()
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "euro-reg-sync",
            "Euro reg sync",
            24,
            self.user,
            structure_config={
                "group_stage": {
                    "number_of_groups": 6,
                    "contestants_qualifying_per_group": 2,
                    "remaining_spots_strategy": "HighestPlaceWithinGroup",
                    "contestants_advancing": 16,
                }
            },
            has_third_place=True,
        )
        self.bracket.metadata = {
            "tournament_type": "euro_2024",
            "third_place_combinations": self.lookup,
        }
        self.bracket.save()

        self.contestants: list[BracketContestant] = []
        for i in range(24):
            c = Contestant.objects.create(
                identifier=f"e{i}",
                name=f"E{i}",
                created_by=self.user,
            )
            self.contestants.append(
                BracketContestant.objects.create(
                    bracket=self.bracket, contestant=c, seed=i + 1
                )
            )

        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        apply_knockout_fill_to_stage(
            KnockoutStage.objects.get(pk=first_ko.pk),
            build_r16_group_knockout_mapping(),
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

    def test_cdef_resolves_third_place_opponents(self):
        """CDEF thirds: B1 vs F3, F1 vs C3, E1 vs D3, C1 vs E3."""
        gp = {}
        for i, letter in enumerate("ABCDEF"):
            gp[letter] = {
                "1": self._bc_for_group_slot(i, 0),
                "2": self._bc_for_group_slot(i, 1),
                "3": self._bc_for_group_slot(i, 2),
            }

        third_letters = ["C", "D", "E", "F"]
        third_advancers = [gp[L]["3"] for L in third_letters]

        metadata = {
            "group_positions": gp,
            "third_place_advancers": third_advancers,
        }
        self.ub.metadata = metadata
        self.ub.save()

        sync_first_knockout_from_group_picks(self.ub)

        placements = _placement_map(self.bracket, metadata)
        third_codes = _third_place_group_codes(self.bracket, metadata, placements)
        pairings = _wc_third_place_pairings(self.bracket, third_codes)
        self.assertEqual(
            pairings,
            {"1B": "3F", "1C": "3E", "1E": "3D", "1F": "3C"},
        )

        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )

        # Fixed pairings
        m1 = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=1)
        self.assertEqual(m1.contestant1_id, gp["A"]["1"])
        self.assertEqual(m1.contestant2_id, gp["C"]["2"])

        m4 = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=4)
        self.assertEqual(m4.contestant1_id, gp["D"]["2"])
        self.assertEqual(m4.contestant2_id, gp["E"]["2"])

        m5 = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=5)
        self.assertEqual(m5.contestant1_id, gp["D"]["1"])
        self.assertEqual(m5.contestant2_id, gp["F"]["2"])

        m8 = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=8)
        self.assertEqual(m8.contestant1_id, gp["A"]["2"])
        self.assertEqual(m8.contestant2_id, gp["B"]["2"])

        # Third-place pairings (not literal template codes)
        m2 = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=2)
        self.assertEqual(m2.contestant1_id, gp["B"]["1"])
        self.assertEqual(m2.contestant2_id, gp["F"]["3"])

        m3 = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=3)
        self.assertEqual(m3.contestant1_id, gp["F"]["1"])
        self.assertEqual(m3.contestant2_id, gp["C"]["3"])

        m6 = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=6)
        self.assertEqual(m6.contestant1_id, gp["E"]["1"])
        self.assertEqual(m6.contestant2_id, gp["D"]["3"])

        m7 = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=7)
        self.assertEqual(m7.contestant1_id, gp["C"]["1"])
        self.assertEqual(m7.contestant2_id, gp["E"]["3"])
