"""Potential (max achievable) score vs a partial master bracket."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketContestant, GroupStage, KnockoutStage, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket
from brackets.api.serializers import bracket_groups_preview
from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
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
        # Single-elim without groups: first-round matchup overlap is not scored;
        # only later rounds (here, the final) earn knockout pick points.
        expected = 2 * ko_pts + self.bracket.points_champion
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

    def test_group_open_slots_ignored_after_knockout_results(self):
        """Once the master has knockout winners, group upside is locked in."""
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "pot-gk-ko",
            "Pot GK KO",
            8,
            self.user,
        )
        gs = GroupStage.objects.get(bracket=bracket)
        gs.points_per_exact_position = 1
        gs.points_per_advancer = 0
        gs.save(update_fields=["points_per_exact_position", "points_per_advancer"])

        for i in range(8):
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"C{i + 1}", seed=i + 1
            )

        master = bracket.get_master_bracket()
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        ub.metadata = {
            "group_positions": {
                "A": {"1": 1, "2": 2, "3": 3, "4": 4},
                "B": {"1": 5, "2": 6, "3": 7, "4": 8},
            }
        }
        ub.save()
        master.metadata = {"group_positions": {"A": {"1": 99}}}
        master.save()
        ensure_knockout_structure_for_user_bracket(master)
        sync_first_knockout_from_group_picks(ub)

        first_ko = (
            bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        mm = master.matchup_set.filter(stage=first_ko, position=1).first()
        self.assertIsNotNone(mm)
        mm.contestant1_id = 1
        mm.contestant2_id = 2
        mm.winner_id = 1
        mm.save(update_fields=["contestant1", "contestant2", "winner"])

        from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
        from brackets.utils.potential_score import group_base_for_potential_scores

        ctx = load_leaderboard_scoring_context(bracket)
        group_base = int(group_base_for_potential_scores([ub], ctx, master)[0])
        self.assertEqual(group_base, 0)
        # Open group slots (positions 2–4) would inflate to 3 before any KO result.
        self.assertNotEqual(calculate_potential_score(ub), 3)

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

    def test_conflicting_teams_only_one_counts_past_master_meeting(self):
        """Teams that meet in the master cannot both earn later knockout potential."""
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "pot-conflict-8",
            "Pot conflict 8",
            8,
            self.user,
            has_third_place=True,
            structure_config={
                "points_champion": 10,
                "points_third_place_winner": 5,
                "knockout": {"points_per_correct_pick": 2},
            },
        )
        teams = [
            BracketContestant.objects.create(
                bracket=bracket, name_override=name, seed=i + 1
            )
            for i, name in enumerate(
                ["Portugal", "Spain", "T3", "T4", "T5", "T6", "T7", "T8"]
            )
        ]
        por, esp = teams[0], teams[1]
        master = bracket.get_master_bracket()
        ub = UserBracket.objects.create(
            bracket=bracket, user=self.user, is_master=False
        )
        ensure_knockout_structure_for_user_bracket(master)
        ensure_knockout_structure_for_user_bracket(ub)

        ko_stages = list(
            bracket.stages.filter(stage_type="KNOCKOUT").order_by("order")
        )
        qf, sf, final = ko_stages[0], ko_stages[1], ko_stages[2]
        third = ko_stages[3]

        def fill_match(ub_obj, stage, position, c1, c2, winner):
            m = ub_obj.matchup_set.get(stage=stage, position=position)
            m.contestant1, m.contestant2, m.winner = c1, c2, winner
            m.save(update_fields=["contestant1", "contestant2", "winner"])

        t = teams
        fill_match(ub, qf, 1, por, t[2], por)
        fill_match(ub, qf, 2, t[3], t[4], t[3])
        fill_match(ub, qf, 3, esp, t[5], esp)
        fill_match(ub, qf, 4, t[6], t[7], t[6])
        fill_match(ub, sf, 1, por, t[3], t[3])
        fill_match(ub, sf, 2, esp, t[6], t[6])
        fill_match(ub, final, 1, t[3], t[6], t[3])
        fill_match(ub, third, 1, por, esp, esp)

        mm = master.matchup_set.get(stage=qf, position=1)
        mm.contestant1, mm.contestant2 = por, esp
        mm.winner = None
        mm.save(update_fields=["contestant1", "contestant2", "winner"])

        potential_open = calculate_potential_score(ub)

        mm.winner = por
        mm.save(update_fields=["winner"])
        potential_if_portugal_wins = calculate_potential_score(ub)

        self.assertGreater(potential_open, potential_if_portugal_wins)
        self.assertGreaterEqual(potential_open, ub.calculate_score(master=master))

    def test_potential_equals_current_when_master_fully_decided(self):
        """No undecided matchups → potential is just the current score."""
        t1, t2, t3, t4 = self.teams
        r1, final = self._ko_stages()

        for stage, pairs in [(r1, [(1, t1, t2), (2, t3, t4)])]:
            for pos, a, b in pairs:
                m = self.ub.matchup_set.get(stage=stage, position=pos)
                m.contestant1, m.contestant2 = a, b
                m.save(update_fields=["contestant1", "contestant2"])
            for pos, winner in [(1, t1), (2, t3)]:
                m = self.ub.matchup_set.get(stage=stage, position=pos)
                m.winner = winner
                m.save(update_fields=["winner"])

        fm = self.ub.matchup_set.get(stage=final, position=1)
        fm.contestant1, fm.contestant2, fm.winner = t1, t3, t1
        fm.save(update_fields=["contestant1", "contestant2", "winner"])

        for stage, pairs in [(r1, [(1, t1, t2), (2, t3, t4)])]:
            for pos, a, b in pairs:
                m = self.master.matchup_set.get(stage=stage, position=pos)
                m.contestant1, m.contestant2 = a, b
                m.save(update_fields=["contestant1", "contestant2"])
            for pos, winner in [(1, t1), (2, t3)]:
                m = self.master.matchup_set.get(stage=stage, position=pos)
                m.winner = winner
                m.save(update_fields=["winner"])
        mm = self.master.matchup_set.get(stage=final, position=1)
        mm.contestant1, mm.contestant2, mm.winner = t1, t3, t1
        mm.save(update_fields=["contestant1", "contestant2", "winner"])

        self.ub.leaderboard_score = self.ub.calculate_score(master=self.master)
        self.ub.save(update_fields=["leaderboard_score"])

        self.assertEqual(
            calculate_potential_score(self.ub),
            self.ub.leaderboard_score,
        )

    def test_scores_compute_when_downstream_shells_empty(self):
        """Empty QF/SF/F slots must not block potential points."""
        t1, t2, t3, t4 = self.teams
        semi, final = self._ko_stages()
        mm = self.master.matchup_set.get(stage=semi, position=2)
        mm.contestant1, mm.contestant2 = t3, t4
        mm.winner = None
        mm.save(update_fields=["contestant1", "contestant2", "winner"])

        self.ub.leaderboard_score = self.ub.calculate_score(master=self.master)
        self.ub.save(update_fields=["leaderboard_score"])

        potential = calculate_potential_score(self.ub)
        self.assertIsNotNone(potential)
        self.assertGreaterEqual(potential, self.ub.leaderboard_score)

    def test_potential_scores_persist_without_rank_cap(self):
        """Potential points persist even when rank enumeration is capped out."""
        from brackets.utils.potential_knockout import prepare_knockout_potential
        from brackets.utils.potential_rank import (
            MAX_UNDECIDED_MATCHUPS,
            compute_potential_ranks_for_bracket,
        )
        from brackets.utils.potential_score import (
            compute_potential_scores_for_bracket,
            persist_potential_scores_for_bracket,
        )

        t1, t2, t3, t4 = self.teams
        semi, final = self._ko_stages()
        mm = self.master.matchup_set.get(stage=semi, position=2)
        mm.contestant1, mm.contestant2 = t3, t4
        mm.winner = None
        mm.save(update_fields=["contestant1", "contestant2", "winner"])

        self.ub.submitted_at = timezone.now()
        self.ub.save(update_fields=["submitted_at"])

        scores = compute_potential_scores_for_bracket(self.bracket)
        self.assertIsNotNone(scores)
        self.assertIn(self.ub.id, scores)

        ranks = compute_potential_ranks_for_bracket(
            self.bracket, cap=MAX_UNDECIDED_MATCHUPS
        )
        self.assertIsNotNone(ranks)

        persist_potential_scores_for_bracket(self.bracket)
        self.ub.refresh_from_db()
        self.assertEqual(self.ub.leaderboard_potential, scores[self.ub.id])

        ctx = load_leaderboard_scoring_context(self.bracket)
        prepared = prepare_knockout_potential(ctx, [self.ub])
        self.assertIsNotNone(prepared)
        if prepared.branchable > 0:
            capped_ranks = compute_potential_ranks_for_bracket(self.bracket, cap=0)
            self.assertIsNotNone(capped_ranks)
            self.assertIsNone(capped_ranks[self.ub.id])
            scores_after_cap = compute_potential_scores_for_bracket(self.bracket)
            self.assertEqual(scores_after_cap[self.ub.id], scores[self.ub.id])

    def test_backtrack_agrees_with_exhaustive_max(self):
        """Potential points backtrack must match max over all master completions."""
        import numpy as np

        from brackets.utils.potential_knockout import (
            completion_totals_vector,
            enumerate_completions,
            max_potential_scores_backtrack,
            prepare_knockout_potential,
        )

        t1, t2, t3, t4 = self.teams
        semi, final = self._ko_stages()
        mm = self.master.matchup_set.get(stage=semi, position=2)
        mm.contestant1, mm.contestant2 = t3, t4
        mm.winner = None
        mm.save(update_fields=["contestant1", "contestant2", "winner"])

        ctx = load_leaderboard_scoring_context(self.bracket)
        prepared = prepare_knockout_potential(ctx, [self.ub])
        self.assertIsNotNone(prepared)

        backtrack = max_potential_scores_backtrack(prepared.tree, prepared.scoring)
        exhaustive = np.full(len(prepared.scoring.current_totals), -1.0, dtype=np.float64)

        def on_completion(state):
            np.maximum(
                exhaustive,
                completion_totals_vector(state, prepared.scoring),
                out=exhaustive,
            )

        enumerate_completions(prepared.tree, on_completion)
        np.testing.assert_allclose(backtrack, exhaustive)

    def test_batch_max_matches_backtrack(self):
        """Production path (batch) must agree with backtrack on small trees."""
        import numpy as np

        from brackets.utils.potential_knockout import (
            max_potential_scores_backtrack,
            max_potential_scores_batch,
            prepare_knockout_potential,
        )

        t1, t2, t3, t4 = self.teams
        semi, final = self._ko_stages()
        mm = self.master.matchup_set.get(stage=semi, position=2)
        mm.contestant1, mm.contestant2 = t3, t4
        mm.winner = None
        mm.save(update_fields=["contestant1", "contestant2", "winner"])

        ctx = load_leaderboard_scoring_context(self.bracket)
        prepared = prepare_knockout_potential(ctx, [self.ub])
        self.assertIsNotNone(prepared)

        batch = max_potential_scores_batch(
            prepared.tree,
            prepared.scoring,
            champ_pts=prepared.champ_pts,
            third_pts=prepared.third_pts,
        )
        backtrack = max_potential_scores_backtrack(prepared.tree, prepared.scoring)
        np.testing.assert_allclose(batch, backtrack)
