import unittest

from brackets.utils.fwc26_regulations import (
    build_third_place_combinations_lookup,
    load_knockout_matchups_raw,
    load_third_place_combinations_raw,
    parse_knockout_matchups_tsv,
    teams_to_bit_vector,
)


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

    def test_knockout_extract_covers_r32_through_semis(self):
        raw = load_knockout_matchups_raw()
        rows = parse_knockout_matchups_tsv(raw)
        self.assertEqual(len(rows), 30)
        m73 = next(r for r in rows if r["match_no"] == "M73")
        self.assertEqual(m73["round"], "Round of 32")
        self.assertIn("2A", m73["team_a"])
        self.assertIn("2B", m73["team_b"])
