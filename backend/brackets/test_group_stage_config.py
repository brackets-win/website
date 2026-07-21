"""Group stage pick requirements derived from GroupStage rows."""

from django.test import TestCase

from brackets.models import Bracket, BracketContestant, GroupStage
from brackets.utils.bracket_completeness import user_bracket_is_complete
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.models import KnockoutStage
from brackets.utils.bracket_admin_update import apply_stage_admin_patch
from brackets.utils.group_stage_config import (
    group_stage_pick_requirements,
    resolve_group_contestants_advancing,
)
from brackets.models import User, UserBracket


class GroupStagePickRequirementsTests(TestCase):
    def test_factory_16_team_bracket(self):
        user = User.objects.create_user(username="u", password="x")
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "g16", "G16", 16, user
        )
        gs = GroupStage.objects.get(bracket=bracket)
        self.assertEqual(gs.contestants_qualifying_per_group, 2)
        ranks, third = group_stage_pick_requirements(gs)
        self.assertEqual(ranks, 2)
        self.assertEqual(third, 0)

    def test_world_cup_style_advancing(self):
        user = User.objects.create_user(username="u2", password="x")
        bracket = Bracket.objects.create(
            identifier="wc-style",
            name="WC style",
            created_by=user,
        )
        gs = GroupStage.objects.create(
            bracket=bracket,
            name="Groups",
            order=1,
            stage_type="GROUP",
            number_of_contestants=48,
            contestants_advancing=32,
            number_of_groups=12,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
        )
        ranks, third = group_stage_pick_requirements(gs)
        self.assertEqual(ranks, 3)
        self.assertEqual(third, 8)

    def test_qualifying_only_skips_third_slot_requirement(self):
        user = User.objects.create_user(username="u-qo", password="x")
        bracket = Bracket.objects.create(
            identifier="euro-qo",
            name="Euro QO",
            created_by=user,
        )
        gs = GroupStage.objects.create(
            bracket=bracket,
            name="Groups",
            order=1,
            stage_type="GROUP",
            number_of_contestants=24,
            contestants_advancing=16,
            number_of_groups=6,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
            remaining_spots_strategy="HighestPlaceWithinGroup",
            group_position_picking="qualifying_only",
        )
        from brackets.utils.group_stage_config import (
            group_stage_exact_placement_count,
            group_stage_scorable_ranks,
        )

        ranks, third = group_stage_pick_requirements(gs)
        self.assertEqual(ranks, 2)
        self.assertEqual(third, 4)
        self.assertEqual(group_stage_scorable_ranks(gs), 2)
        # 6 groups × 2 ranks + 4 third-place rail picks
        self.assertEqual(group_stage_exact_placement_count(gs), 16)

    def test_completeness_uses_qualifying_not_hardcoded(self):
        user = User.objects.create_user(username="u3", password="x")
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "g16b", "G16b", 16, user
        )
        gs = GroupStage.objects.get(bracket=bracket)
        gs.contestants_qualifying_per_group = 3
        gs.contestants_advancing = 12  # 4 groups × 3
        gs.save()
        # Create contestants so bracket_groups_preview returns groups
        for i in range(16):
            BracketContestant.objects.create(bracket=bracket, name_override=f"T{i+1}", seed=i + 1)
        ub = UserBracket.objects.create(user=user, bracket=bracket)
        complete, reason = user_bracket_is_complete(ub)
        self.assertFalse(complete)
        self.assertIn("group", (reason or "").lower())

    def test_admin_stage_save_preserves_third_place_advancing_total(self):
        user = User.objects.create_user(username="u4", password="x")
        bracket = Bracket.objects.create(
            identifier="wc-admin",
            name="WC admin",
            created_by=user,
            has_third_place_match=True,
            metadata={"tournament_type": "world_cup_2026"},
        )
        gs = GroupStage.objects.create(
            bracket=bracket,
            name="Groups",
            order=1,
            stage_type="GROUP",
            number_of_contestants=48,
            contestants_advancing=32,
            number_of_groups=12,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
            remaining_spots_strategy="HighestPlaceWithinGroup",
        )
        KnockoutStage.objects.create(
            bracket=bracket,
            name="Round of 32",
            order=2,
            stage_type="KNOCKOUT",
            number_of_contestants=32,
            contestants_advancing=16,
            is_final=False,
        )
        apply_stage_admin_patch(
            gs,
            {
                "id": gs.id,
                "contestants_qualifying_per_group": 2,
                "number_of_groups": 12,
            },
        )
        gs.refresh_from_db()
        self.assertEqual(gs.contestants_advancing, 32)
        ranks, third = group_stage_pick_requirements(gs)
        self.assertEqual(third, 8)
        self.assertEqual(ranks, 3)

    def test_resolve_group_advancing_from_first_knockout_size(self):
        user = User.objects.create_user(username="u5", password="x")
        bracket = Bracket.objects.create(
            identifier="wc-resolve",
            name="WC resolve",
            created_by=user,
            has_third_place_match=True,
        )
        gs = GroupStage.objects.create(
            bracket=bracket,
            name="Groups",
            order=1,
            stage_type="GROUP",
            number_of_contestants=48,
            contestants_advancing=24,
            number_of_groups=12,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
            remaining_spots_strategy="HighestPlaceWithinGroup",
        )
        KnockoutStage.objects.create(
            bracket=bracket,
            name="Round of 32",
            order=2,
            stage_type="KNOCKOUT",
            number_of_contestants=32,
            contestants_advancing=16,
            is_final=False,
        )
        self.assertEqual(resolve_group_contestants_advancing(gs), 32)
