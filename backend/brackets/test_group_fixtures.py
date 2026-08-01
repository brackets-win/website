from django.test import SimpleTestCase

from brackets.utils.group_fixtures import (
    generate_round_robin,
    group_positions_from_fixtures,
    standings_for_group,
)


class GroupFixturesTests(SimpleTestCase):
    def test_single_round_robin_count(self):
        fixtures = generate_round_robin(
            [1, 2, 3, 4],
            matches_per_contestant=3,
            group_code="A",
        )
        self.assertEqual(len(fixtures), 6)

    def test_home_and_away_count(self):
        fixtures = generate_round_robin(
            [1, 2, 3, 4],
            matches_per_contestant=6,
            group_code="B",
        )
        self.assertEqual(len(fixtures), 12)

    def test_rank_by_pts_then_gd_then_gs(self):
        # Same PTS and GD; higher GS ranks first.
        fixtures = [
            {"home_id": 1, "away_id": 4, "home_score": 2, "away_score": 1},
            {"home_id": 2, "away_id": 3, "home_score": 1, "away_score": 0},
        ]
        rows = standings_for_group([1, 2, 3, 4], fixtures)
        self.assertEqual(
            [r["contestant_id"] for r in rows],
            [1, 2, 4, 3],
        )
        self.assertEqual(rows[0]["pts"], 3)
        self.assertEqual(rows[0]["gd"], 1)
        self.assertEqual(rows[0]["gf"], 2)
        self.assertEqual(rows[0]["ga"], 1)
        self.assertEqual(rows[1]["pts"], 3)
        self.assertEqual(rows[1]["gd"], 1)
        self.assertEqual(rows[1]["gf"], 1)

        # GD breaks the PTS tie: team 5 (+3) above team 6 (+1).
        fixtures2 = [
            {"home_id": 5, "away_id": 7, "home_score": 3, "away_score": 0},
            {"home_id": 6, "away_id": 8, "home_score": 1, "away_score": 0},
        ]
        rows2 = standings_for_group([5, 6, 7, 8], fixtures2)
        self.assertEqual(
            [r["contestant_id"] for r in rows2[:2]],
            [5, 6],
        )
        self.assertEqual(rows2[0]["gd"], 3)
        self.assertEqual(rows2[1]["gd"], 1)

    def test_positions_map_from_fixtures(self):
        preview = [
            {
                "code": "A",
                "teams": [{"id": 10}, {"id": 20}, {"id": 30}, {"id": 40}],
            }
        ]
        fixtures = {
            "A": [
                {
                    "home_id": 10,
                    "away_id": 20,
                    "home_score": 3,
                    "away_score": 0,
                },
                {
                    "home_id": 30,
                    "away_id": 40,
                    "home_score": 1,
                    "away_score": 0,
                },
            ]
        }
        positions = group_positions_from_fixtures(preview, fixtures)
        self.assertEqual(positions["A"]["1"], 10)
        self.assertEqual(positions["A"]["2"], 30)
