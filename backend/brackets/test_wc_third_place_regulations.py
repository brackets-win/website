"""
World Cup third-place knockout seeding must use ``third_place_combinations.txt``
via a bit-vector lookup — not random assignment or literal ``3X`` template codes.
"""

from django.test import TestCase

from brackets.models import BracketContestant, Contestant, KnockoutStage, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.fwc26_regulations import (
    build_third_place_combinations_lookup,
    load_third_place_combinations_raw,
    teams_to_bit_vector,
)
from brackets.utils.group_knockout_mapping import set_custom_group_knockout_mapping
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell
from brackets.utils.sync_group_knockout import (
    _placement_map,
    _third_place_group_codes,
    _wc_third_place_pairings,
    sync_first_knockout_from_group_picks,
)


def _regulation_lookup() -> dict:
    return build_third_place_combinations_lookup(load_third_place_combinations_raw())


class WcThirdPlaceRegulationLookupTests(TestCase):
    """Lookup table shape and determinism (file → bracket.metadata)."""

    def test_lookup_has_495_regulation_rows(self):
        self.assertEqual(len(_regulation_lookup()), 495)

    def test_same_eight_groups_always_same_bit_vector_key(self):
        teams = ["3E", "3J", "3I", "3F", "3H", "3G", "3L", "3K"]
        k1 = str(teams_to_bit_vector(teams))
        k2 = str(teams_to_bit_vector(list(reversed(teams))))
        self.assertEqual(k1, k2)

    def test_different_eight_groups_different_keys(self):
        option1 = ["3E", "3J", "3I", "3F", "3H", "3G", "3L", "3K"]
        option2 = ["3H", "3G", "3I", "3D", "3J", "3F", "3L", "3K"]
        lookup = _regulation_lookup()
        m1 = lookup[str(teams_to_bit_vector(option1))]["matchups"]
        m2 = lookup[str(teams_to_bit_vector(option2))]["matchups"]
        self.assertNotEqual(m1["1E"], m2["1E"])

    def test_wc_pairings_returns_exact_matchups_dict_from_lookup(self):
        lookup = _regulation_lookup()
        third_codes = ["3E", "3J", "3I", "3F", "3H", "3G", "3L", "3K"]
        key = str(teams_to_bit_vector(third_codes))
        expected = lookup[key]["matchups"]

        bracket = type("B", (), {"metadata": {"third_place_combinations": lookup}})()
        pairings = _wc_third_place_pairings(bracket, third_codes)
        self.assertEqual(pairings, expected)


class WcThirdPlaceKnockoutSyncTests(TestCase):
    """End-to-end: user picks → bit vector → regulation row → R32 contestants."""

    def setUp(self):
        self.user = User.objects.create_user(username="wc-reg", password="x")
        self.lookup = _regulation_lookup()
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "wc-reg-sync",
            "WC reg sync",
            48,
            self.user,
        )
        self.bracket.metadata = {
            "tournament_type": "world_cup_2026",
            "third_place_combinations": self.lookup,
        }
        self.bracket.save()

        self.contestants: list[BracketContestant] = []
        for i in range(48):
            c = Contestant.objects.create(
                identifier=f"r{i}",
                name=f"T{i}",
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
        set_custom_group_knockout_mapping(
            KnockoutStage.objects.get(pk=first_ko.pk),
            [(1, "E1", "3E"), (7, "A1", "3A")],
        )

        self.ub = self.bracket.userbracket_set.create(
            user=self.user,
            is_master=False,
        )
        ensure_knockout_matchup_shell(self.ub)

    def _bc(self, group_index: int, rank: int) -> int:
        return self.contestants[group_index * 4 + (rank - 1)].id

    def _full_gp(self) -> dict:
        gp = {}
        for i, letter in enumerate("ABCDEFGHIJKL"):
            gp[letter] = {
                "1": self._bc(i, 1),
                "2": self._bc(i, 2),
                "3": self._bc(i, 3),
            }
        return gp

    def test_template_3e_is_not_literal_opponent(self):
        """R32 row ``E1`` vs ``3E`` uses FIFA table for 1E, not group E's third."""
        gp = self._full_gp()
        third_letters = ["E", "J", "I", "F", "H", "G", "L", "K"]
        third_advancers = [gp[L]["3"] for L in third_letters]
        metadata = {
            "group_positions": gp,
            "third_place_advancers": third_advancers,
        }
        self.ub.metadata = metadata
        self.ub.save()

        sync_first_knockout_from_group_picks(self.ub)

        lookup_row = self.lookup[str(teams_to_bit_vector([f"3{L}" for L in third_letters]))]
        opponent_letter = lookup_row["matchups"]["1E"][1]
        expected_third_id = gp[opponent_letter]["3"]

        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        m = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=1)
        self.assertEqual(m.contestant1_id, gp["E"]["1"])
        self.assertEqual(m.contestant2_id, expected_third_id)
        self.assertNotEqual(m.contestant2_id, gp["E"]["3"])

    def test_seven_advancers_does_not_fill_third_place_slots(self):
        gp = self._full_gp()
        third_advancers = [gp[L]["3"] for L in ["E", "J", "I", "F", "H", "G", "L"]]
        metadata = {
            "group_positions": gp,
            "third_place_advancers": third_advancers,
        }
        self.ub.metadata = metadata
        self.ub.save()
        sync_first_knockout_from_group_picks(self.ub)

        first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        m = Matchup.objects.get(user_bracket=self.ub, stage=first_ko, position=1)
        self.assertIsNone(m.contestant2_id)

    def test_third_codes_derived_from_advancer_ids_not_all_group_thirds(self):
        gp = self._full_gp()
        # Only pick 8 specific third-place finishers (option 1 groups)
        third_letters = ["E", "J", "I", "F", "H", "G", "L", "K"]
        third_advancers = [gp[L]["3"] for L in third_letters]
        metadata = {
            "group_positions": gp,
            "third_place_advancers": third_advancers,
        }
        placements = _placement_map(self.bracket, metadata)
        codes = _third_place_group_codes(self.bracket, metadata, placements)
        self.assertEqual(len(codes), 8)
        self.assertEqual(set(codes), {f"3{L}" for L in third_letters})
