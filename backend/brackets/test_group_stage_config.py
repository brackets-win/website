"""Group stage pick requirements derived from GroupStage rows."""

from django.test import TestCase

from brackets.models import Bracket, GroupStage
from brackets.utils.bracket_completeness import user_bracket_is_complete
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.group_stage_config import group_stage_pick_requirements
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

    def test_completeness_uses_qualifying_not_hardcoded(self):
        user = User.objects.create_user(username="u3", password="x")
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "g16b", "G16b", 16, user
        )
        gs = GroupStage.objects.get(bracket=bracket)
        gs.contestants_qualifying_per_group = 3
        gs.contestants_advancing = 12  # 4 groups × 3
        gs.save()
        ub = UserBracket.objects.create(user=user, bracket=bracket)
        complete, reason = user_bracket_is_complete(ub)
        self.assertFalse(complete)
        self.assertIn("group", (reason or "").lower())
