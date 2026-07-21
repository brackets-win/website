"""Scoring highlights include projected first knockout teams from group picks."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.models import BracketContestant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.scoring_highlights import scoring_highlights_for_user_bracket
from brackets.utils.sync_group_knockout import (
    contestants_in_stage_for_scoring,
    sync_first_knockout_from_group_picks,
)

User = get_user_model()


class ScoringHighlightsKnockoutTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.player = User.objects.create_user(username="player", password="x")
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "hl-ko",
            "HL",
            8,
            self.host,
        )
        for i in range(8):
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"C{i + 1}", seed=i + 1
            )
        self.master = UserBracket.objects.get(bracket=self.bracket, is_master=True)
        self.ub = UserBracket.objects.create(
            bracket=self.bracket, user=self.player, is_master=False
        )
        self.first_ko = (
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )

    def test_projected_r32_overlap_without_master_matchup_sync(self):
        gp = {
            "A": {"1": 1, "2": 2, "3": 3, "4": 4},
            "B": {"1": 5, "2": 6, "3": 7, "4": 8},
        }
        self.ub.metadata = {"group_positions": gp}
        self.ub.save()
        sync_first_knockout_from_group_picks(self.ub)

        self.master.metadata = {"group_positions": {"A": {"1": 1, "2": 2}}}
        self.master.save()

        master_r32 = contestants_in_stage_for_scoring(self.master, self.first_ko)
        self.assertIn(1, master_r32)
        self.assertIn(2, master_r32)

        highlights = scoring_highlights_for_user_bracket(self.ub)
        ko_ids = {
            x["contestant_id"] for x in highlights["knockout_contestants"]
        }
        self.assertIn(1, ko_ids)

    def test_qualifying_only_third_rail_exact_highlight(self):
        from brackets.models import Bracket, BracketStage, GroupStage

        bracket = Bracket.objects.create(
            identifier="hl-qo",
            name="HL QO",
            created_by=self.host,
        )
        GroupStage.objects.create(
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
            bracket=bracket, user=self.player, is_master=False
        )
        master.metadata = {
            "group_positions": {"A": {"1": 1, "2": 2}, "B": {"1": 5, "2": 6}},
            "third_place_advancers": [3, 7],
        }
        master.save()
        ub.metadata = {
            "group_positions": {"A": {"1": 1, "2": 2}, "B": {"1": 5, "2": 6}},
            "third_place_advancers": [3, 4],
        }
        ub.save()

        highlights = scoring_highlights_for_user_bracket(ub)
        self.assertIn(3, highlights["group_advancers"])
        self.assertNotIn(4, highlights["group_advancers"])
        self.assertEqual(highlights["group_positions"]["A"]["1"], True)
