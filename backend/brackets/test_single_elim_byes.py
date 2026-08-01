from django.test import TestCase

from brackets.models import BracketContestant, Contestant, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket
from brackets.utils.single_elim_byes import (
    single_elim_bye_count,
    single_elim_field_size,
    single_elim_play_in_count,
)
from brackets.utils.tournament_placement import compute_draw_seeds
from brackets.utils.tournament_teams import (
    apply_tournament_teams,
    tournament_team_capacity,
)


class SingleElimByeMathTests(TestCase):
    def test_forty(self):
        self.assertEqual(single_elim_field_size(40), 64)
        self.assertEqual(single_elim_bye_count(40), 24)
        self.assertEqual(single_elim_play_in_count(40), 16)

    def test_six(self):
        self.assertEqual(single_elim_field_size(6), 8)
        self.assertEqual(single_elim_bye_count(6), 2)
        self.assertEqual(single_elim_play_in_count(6), 4)

    def test_power_of_two(self):
        self.assertEqual(single_elim_bye_count(16), 0)
        self.assertEqual(single_elim_field_size(16), 16)

    def test_bye_draw_pots_thirty_four(self):
        from brackets.utils.single_elim_byes import single_elim_bye_draw_pots

        pots = single_elim_bye_draw_pots(34)
        self.assertEqual(
            [(p["label"], p["size"]) for p in pots],
            [
                ("Bye vs R1 Winners", 2),
                ("Bye", 28),
                ("Round 1", 4),
            ],
        )
        self.assertEqual(pots[0]["seeds"], [1, 2])
        self.assertEqual(pots[2]["seeds"], [31, 32, 33, 34])

    def test_bye_draw_pots_six_omits_pure_bye(self):
        from brackets.utils.single_elim_byes import single_elim_bye_draw_pots

        pots = single_elim_bye_draw_pots(6)
        self.assertEqual(
            [(p["label"], p["size"]) for p in pots],
            [
                ("Bye vs R1 Winners", 2),
                ("Round 1", 4),
            ],
        )


class SingleElimStageNameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="namhost", password="x")

    def test_non_power_of_two_uses_numbered_rounds(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "se-34",
            "Thirty Four",
            34,
            self.user,
        )
        names = list(
            bracket.stages.filter(stage_type="KNOCKOUT")
            .order_by("order")
            .values_list("name", flat=True)
        )
        self.assertEqual(
            names,
            [
                "Round 1",
                "Round 2",
                "Round 3",
                "Quarterfinals",
                "Semifinals",
                "Final",
            ],
        )

    def test_power_of_two_keeps_round_of_n(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "se-32",
            "Thirty Two",
            32,
            self.user,
        )
        names = list(
            bracket.stages.filter(stage_type="KNOCKOUT")
            .order_by("order")
            .values_list("name", flat=True)
        )
        self.assertEqual(
            names,
            [
                "Round of 32",
                "Round of 16",
                "Quarterfinals",
                "Semifinals",
                "Final",
            ],
        )

    def test_sync_renames_legacy_round_of_labels(self):
        from brackets.utils.single_elim_byes import sync_single_elim_knockout_stage_names

        bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "se-34-legacy",
            "Legacy",
            34,
            self.user,
        )
        first = (
            bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        first.name = "Round of 64"
        first.save(update_fields=["name"])
        sync_single_elim_knockout_stage_names(bracket)
        first.refresh_from_db()
        self.assertEqual(first.name, "Round 1")


class SingleElimByeBracketTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="byehost", password="x")

    def test_factory_roster_and_field(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "se-40",
            "Forty",
            40,
            self.user,
        )
        self.assertEqual(bracket.metadata.get("roster_size"), 40)
        first = (
            bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        self.assertEqual(first.number_of_contestants, 64)
        self.assertEqual(tournament_team_capacity(bracket), 40)

    def test_six_team_byes_propagate(self):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "se-6",
            "Six",
            6,
            self.user,
        )
        teams = [{"name": f"T{i}", "seed": i} for i in range(1, 7)]
        apply_tournament_teams(bracket, teams)
        master = bracket.get_master_bracket()
        first = (
            bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        r1 = list(
            Matchup.objects.filter(user_bracket=master, stage=first).order_by(
                "position"
            )
        )
        self.assertEqual(len(r1), 4)
        bye_games = [
            m for m in r1 if m.contestant1_id is None or m.contestant2_id is None
        ]
        play_games = [
            m
            for m in r1
            if m.contestant1_id is not None and m.contestant2_id is not None
        ]
        self.assertEqual(len(bye_games), 2)
        self.assertEqual(len(play_games), 2)
        for m in bye_games:
            self.assertIsNotNone(m.winner_id)

        second = (
            bracket.stages.filter(stage_type="KNOCKOUT")
            .order_by("order")[1]
        )
        r2 = list(
            Matchup.objects.filter(user_bracket=master, stage=second).order_by(
                "position"
            )
        )
        # Both bye winners should already sit in the round of 4.
        filled = sum(
            1
            for m in r2
            for cid in (m.contestant1_id, m.contestant2_id)
            if cid is not None
        )
        self.assertEqual(filled, 2)

    def test_bye_pot_draw_assigns_top_seeds(self):
        teams = (
            [{"name": f"B{i}", "pot": 1} for i in range(2)]
            + [{"name": f"P{i}", "pot": 2} for i in range(4)]
        )
        out = compute_draw_seeds(
            mode="random_balanced",
            teams=teams,
            structure="SINGLE_ELIM",
            number_of_groups=None,
            teams_per_group=None,
        )
        by_seed = {row["seed"]: row["name"] for row in out}
        self.assertTrue(by_seed[1].startswith("B"))
        self.assertTrue(by_seed[2].startswith("B"))
        self.assertTrue(by_seed[3].startswith("P"))
        self.assertTrue(by_seed[6].startswith("P"))

    def test_three_band_bye_draw_for_thirty_four(self):
        teams = (
            [{"name": f"X{i}", "pot": 1} for i in range(2)]
            + [{"name": f"Y{i}", "pot": 2} for i in range(28)]
            + [{"name": f"Z{i}", "pot": 3} for i in range(4)]
        )
        out = compute_draw_seeds(
            mode="random_balanced",
            teams=teams,
            structure="SINGLE_ELIM",
            number_of_groups=None,
            teams_per_group=None,
        )
        by_seed = {row["seed"]: row["name"] for row in out}
        self.assertTrue(by_seed[1].startswith("X"))
        self.assertTrue(by_seed[2].startswith("X"))
        self.assertTrue(by_seed[3].startswith("Y"))
        self.assertTrue(by_seed[30].startswith("Y"))
        self.assertTrue(by_seed[31].startswith("Z"))
        self.assertTrue(by_seed[34].startswith("Z"))
