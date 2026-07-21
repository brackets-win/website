"""Scoring rules: group exact/advancer, knockout pool, champion, third place."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.models import (
    Bracket,
    BracketContestant,
    BracketStage,
    GroupStage,
    KnockoutStage,
    UserBracket,
)
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell

User = get_user_model()


class ScoringConfigTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="score", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "score-se",
            "Score SE",
            4,
            self.user,
            structure_config={
                "points_champion": 10,
                "knockout": {"points_per_correct_pick": 2},
            },
        )
        self.bracket.points_third_place_winner = 3
        self.bracket.save(update_fields=["points_third_place_winner"])
        self.master = self.bracket.get_master_bracket()
        self.ub = UserBracket.objects.create(
            bracket=self.bracket, user=self.user, is_master=False
        )

    def test_champion_score(self):
        self.bracket.refresh_from_db()
        self.assertEqual(self.bracket.points_champion, 10)

        champ = BracketContestant.objects.create(
            bracket=self.bracket, name_override="Champ", seed=1
        )
        ensure_knockout_matchup_shell(self.master)
        ensure_knockout_matchup_shell(self.ub)
        final = KnockoutStage.objects.get(bracket=self.bracket, is_final=True)
        master_final = self.master.matchup_set.filter(stage=final).first()
        user_final = self.ub.matchup_set.filter(stage=final).first()
        master_final.winner = champ
        master_final.save(update_fields=["winner"])
        user_final.winner = champ
        user_final.save(update_fields=["winner"])

        self.assertEqual(self.ub.calculate_champion_score(), 10)

    def test_group_exact_and_advancer(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "score-gk",
            "Score GK",
            8,
            self.user,
        )
        gs = GroupStage.objects.get(bracket=bracket)
        gs.points_per_exact_position = 1
        gs.points_per_advancer = 5
        gs.save(update_fields=["points_per_exact_position", "points_per_advancer"])

        master = bracket.get_master_bracket()
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        master.metadata = {
            "group_positions": {
                "A": {"1": 1, "2": 2, "3": 3, "4": 4},
                "B": {"1": 5, "2": 6, "3": 7, "4": 8},
            }
        }
        master.save()
        ub.metadata = {
            "group_positions": {
                "A": {"1": 1, "2": 3, "3": 2, "4": 4},
                "B": {"1": 5, "2": 6, "3": 7, "4": 8},
            }
        }
        ub.save()

        group_stage = bracket.stages.filter(stage_type="GROUP").first()
        score = ub.calculate_stage_score(group_stage)
        # 6 exact positions; A has one matching advancer, B has two
        self.assertEqual(score, 6 + 5 + 5 * 2)

    def test_qualifying_only_third_place_rail_earns_exact_points(self):
        """Under Qualifying Only, matched top-n thirds count as exact placements."""
        bracket = Bracket.objects.create(
            identifier="score-qo",
            name="Score QO",
            created_by=self.user,
        )
        gs = GroupStage.objects.create(
            bracket=bracket,
            name="Groups",
            order=1,
            stage_type=BracketStage.StageType.GROUP,
            number_of_contestants=8,
            contestants_advancing=6,
            number_of_groups=2,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
            remaining_spots_strategy="HighestPlaceWithinGroup",
            group_position_picking="qualifying_only",
            points_per_exact_position=1,
            points_per_advancer=0,
        )
        master = bracket.get_master_bracket()
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        master.metadata = {
            "group_positions": {
                "A": {"1": 1, "2": 2},
                "B": {"1": 5, "2": 6},
            },
            "third_place_advancers": [3, 7],
        }
        master.save()
        ub.metadata = {
            "group_positions": {
                "A": {"1": 1, "2": 2},
                "B": {"1": 5, "2": 8},
            },
            "third_place_advancers": [3, 4],
        }
        ub.save()

        score = ub.calculate_stage_score(gs)
        # Exact: A1, A2, B1 (3) + one matching third-place rail pick (3) = 4
        self.assertEqual(score, 4)
