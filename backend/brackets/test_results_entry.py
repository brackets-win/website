"""Unit tests for matchup score legs and results-entry normalization."""

from django.test import SimpleTestCase

from brackets.utils.matchup_scores import (
    aggregate_totals,
    normalize_legs,
    winner_id_from_totals,
)
from brackets.utils.results_entry import normalize_results_entry


class MatchupScoresTests(SimpleTestCase):
    def test_normalize_two_legs(self):
        legs = normalize_legs([[1, 0], [0, 2]], expected_legs=2)
        self.assertEqual(legs, [[1, 0], [0, 2]])
        self.assertEqual(aggregate_totals(legs), (1, 2))
        self.assertEqual(winner_id_from_totals(10, 20, 1, 2), 20)

    def test_incomplete_leg_rejected_half(self):
        with self.assertRaises(ValueError):
            normalize_legs([[1, None]], expected_legs=1)

    def test_empty_legs_ok(self):
        legs = normalize_legs([[None, None], [None, None]], expected_legs=2)
        self.assertEqual(aggregate_totals(legs), (None, None))
        self.assertIsNone(winner_id_from_totals(1, 2, None, None))


class ResultsEntryTests(SimpleTestCase):
    def test_defaults(self):
        self.assertEqual(
            normalize_results_entry(None),
            {"group": "standings", "knockout": "winner"},
        )

    def test_normalize(self):
        self.assertEqual(
            normalize_results_entry({"group": "fixtures", "knockout": "score"}),
            {"group": "fixtures", "knockout": "score"},
        )
