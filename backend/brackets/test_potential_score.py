"""Potential (max achievable) score vs a partial master bracket."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.models import BracketContestant, GroupStage, KnockoutStage, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket
from brackets.api.serializers import bracket_groups_preview
from brackets.utils.potential_score import calculate_potential_score
from brackets.utils.sync_group_knockout import sync_first_knockout_from_group_picks

User = get_user_model()


class PotentialScoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pot", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "pot-se-4",
            "Pot SE 4",
            4,
            self.user,
            structure_config={
                "points_champion": 10,
                "knockout": {"points_per_correct_pick": 2},
            },
        )
        self.master = self.bracket.get_master_bracket()
        self.ub = UserBracket.objects.create(
            bracket=self.bracket, user=self.user, is_master=False
        )
        self.teams = []
        for i in range(4):
            self.teams.append(
                BracketContestant.objects.create(
                    bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
                )
            )
        ensure_knockout_structure_for_user_bracket(self.master)
        ensure_knockout_structure_for_user_bracket(self.ub)

    def _ko_stages(self):
        return list(
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order")
        )

    def test_empty_master_matches_high_potential(self):
        """Before master is filled, user can still max out knockout overlap + champion."""
        t1, t2, t3, t4 = self.teams
        r1, final = self._ko_stages()

        ko_pts = KnockoutStage.objects.get(pk=r1.pk).points_per_correct_pick
        for stage, pairs in [
            (r1, [(1, t1, t2), (2, t3, t4)]),
        ]:
            for pos, a, b in pairs:
                m = self.ub.matchup_set.get(stage=stage, position=pos)
                m.contestant1, m.contestant2 = a, b
                m.save(update_fields=["contestant1", "contestant2"])
            if stage == r1:
                for pos, winner in [(1, t1), (2, t3)]:
                    m = self.ub.matchup_set.get(stage=stage, position=pos)
                    m.winner = winner
                    m.save(update_fields=["winner"])

        fm = self.ub.matchup_set.get(stage=final, position=1)
        fm.contestant1, fm.contestant2 = t1, t3
        fm.winner = t1
        fm.save(update_fields=["contestant1", "contestant2", "winner"])

        potential = calculate_potential_score(self.ub)
        expected = (4 + 2) * ko_pts + self.bracket.points_champion
        self.assertEqual(potential, expected)

    def test_master_r32_elimination_lowers_potential(self):
        t1, t2, t3, t4 = self.teams
        r1, final = self._ko_stages()

        m1 = self.ub.matchup_set.get(stage=r1, position=1)
        m1.contestant1, m1.contestant2, m1.winner = t1, t2, t1
        m1.save(update_fields=["contestant1", "contestant2", "winner"])
        m2 = self.ub.matchup_set.get(stage=r1, position=2)
        m2.contestant1, m2.contestant2, m2.winner = t3, t4, t3
        m2.save(update_fields=["contestant1", "contestant2", "winner"])

        mm1 = self.master.matchup_set.get(stage=r1, position=1)
        mm1.contestant1, mm1.contestant2, mm1.winner = t1, t2, t2
        mm1.save(update_fields=["contestant1", "contestant2", "winner"])

        potential = calculate_potential_score(self.ub)
        actual = self.ub.calculate_score()
        ko_pts = KnockoutStage.objects.get(pk=r1.pk).points_per_correct_pick
        full = (4 + 2) * ko_pts + self.bracket.points_champion
        self.assertLess(potential, full)
        self.assertGreaterEqual(potential, actual)

    def test_group_exact_open_slot_counts_toward_potential(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "pot-gk",
            "Pot GK",
            8,
            self.user,
        )
        gs = GroupStage.objects.get(bracket=bracket)
        gs.points_per_exact_position = 1
        gs.points_per_advancer = 0
        gs.save(update_fields=["points_per_exact_position", "points_per_advancer"])

        master = bracket.get_master_bracket()
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        ub.metadata = {
            "group_positions": {
                "A": {"1": 1, "2": 2, "3": 3, "4": 4},
            }
        }
        ub.save()
        master.metadata = {"group_positions": {"A": {"1": 99}}}
        master.save()

        # Master locked position 1; positions 2–4 still achievable.
        self.assertEqual(calculate_potential_score(ub), 3)
        self.assertEqual(ub.calculate_score(), 0)

    def test_wc_style_four_group_slots_not_three(self):
        """12 groups × 4 finish slots × 1 pt = 48 (not 36 from ranks_required only)."""
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "pot-wc-slots",
            "Pot WC slots",
            48,
            self.user,
        )
        gs = GroupStage.objects.get(bracket=bracket)
        gs.number_of_groups = 12
        gs.points_per_exact_position = 1
        gs.points_per_advancer = 0
        gs.save(
            update_fields=[
                "number_of_groups",
                "points_per_exact_position",
                "points_per_advancer",
            ]
        )
        for i in range(48):
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"C{i + 1}", seed=i + 1
            )
        master = bracket.get_master_bracket()
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        gp = {}
        for g in range(12):
            code = chr(65 + g)
            base = g * 4 + 1
            gp[code] = {
                "1": base,
                "2": base + 1,
                "3": base + 2,
                "4": base + 3,
            }
        ub.metadata = {"group_positions": gp}
        ub.save()

        group_only = 0
        for group in bracket_groups_preview(bracket):
            code = group["code"]
            row = gp[code]
            for pos in range(1, 5):
                if row.get(str(pos)) is not None:
                    group_only += 1

        self.assertEqual(group_only, 48)
        self.assertEqual(calculate_potential_score(ub), 48)

    def test_potential_is_at_least_actual_with_projected_r32_overlap(self):
        """Knockout scoring credits projected R32 teams; potential must not lag actual."""
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "pot-r32-overlap",
            "Pot R32 overlap",
            8,
            self.user,
            structure_config={"knockout": {"points_per_correct_pick": 2}},
        )
        for i in range(8):
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"C{i + 1}", seed=i + 1
            )
        master = bracket.get_master_bracket()
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        gp = {
            "A": {"1": 1, "2": 2, "3": 3, "4": 4},
            "B": {"1": 5, "2": 6, "3": 7, "4": 8},
        }
        ub.metadata = {"group_positions": gp}
        ub.save()
        sync_first_knockout_from_group_picks(ub)

        master.metadata = {"group_positions": {"A": {"1": 1, "2": 2}}}
        master.save()

        actual = ub.calculate_score()
        potential = calculate_potential_score(ub)
        self.assertGreater(actual, 0)
        self.assertGreaterEqual(potential, actual)
