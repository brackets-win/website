"""Potential rank — best achievable finish across master knockout completions."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketChallenge, BracketContestant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.group_results_mode import set_group_results_mode_on_metadata
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket
from brackets.utils.leaderboard_scoring import (
    load_leaderboard_scoring_context,
    on_master_bracket_changed,
    read_stored_leaderboard_scores,
    refresh_all_submitted_leaderboard_scores_for_bracket,
)
from brackets.utils.potential_rank import (
    competition_ranks_batch,
    compute_potential_ranks_for_bracket,
)
from brackets.utils.potential_score import compute_potential_scores_for_bracket
from brackets.utils.sync_group_knockout import sync_first_knockout_from_group_picks

User = get_user_model()


class PotentialRankTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "pot-rank-se4",
            "Pot Rank SE4",
            4,
            self.host,
            structure_config={
                "points_champion": 10,
                "knockout": {"points_per_correct_pick": 1},
            },
        )
        self.challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=self.bracket,
            created_by=self.host,
            join_code="POTRANK1",
        )
        self.master = self.bracket.get_master_bracket()
        self.teams = [
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(4)
        ]
        ensure_knockout_structure_for_user_bracket(self.master)

    def _ko_stages(self):
        return list(
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order")
        )

    def _fill_user_bracket(self, ub, *, sf1, sf2, final_winner):
        """sf1/sf2/final_winner are winning team objects from self.teams."""
        semi, final = self._ko_stages()
        ensure_knockout_structure_for_user_bracket(ub)
        t1, t2, t3, t4 = self.teams

        m1 = ub.matchup_set.get(stage=semi, position=1)
        m1.contestant1, m1.contestant2 = t1, t2
        m1.winner = sf1
        m1.save(update_fields=["contestant1", "contestant2", "winner"])

        m2 = ub.matchup_set.get(stage=semi, position=2)
        m2.contestant1, m2.contestant2 = t3, t4
        m2.winner = sf2
        m2.save(update_fields=["contestant1", "contestant2", "winner"])

        fm = ub.matchup_set.get(stage=final, position=1)
        fm.contestant1 = sf1
        fm.contestant2 = sf2
        fm.winner = final_winner
        fm.save(update_fields=["contestant1", "contestant2", "winner"])

    def _submit(self, username, *, sf1, sf2, final_winner):
        user = User.objects.create_user(username=username, password="x")
        ub = UserBracket.objects.create(
            user=user,
            bracket=self.bracket,
            challenge=self.challenge,
            submitted_at=timezone.now(),
        )
        self._fill_user_bracket(ub, sf1=sf1, sf2=sf2, final_winner=final_winner)
        return ub

    def _set_master_partial(self, *, sf1_winner, sf2_winner=None, final_winner=None):
        semi, final = self._ko_stages()
        t1, t2, t3, t4 = self.teams

        m1 = self.master.matchup_set.get(stage=semi, position=1)
        m1.contestant1, m1.contestant2, m1.winner = t1, t2, sf1_winner
        m1.save(update_fields=["contestant1", "contestant2", "winner"])

        m2 = self.master.matchup_set.get(stage=semi, position=2)
        m2.contestant1, m2.contestant2 = t3, t4
        m2.winner = sf2_winner
        m2.save(update_fields=["contestant1", "contestant2", "winner"])

        fm = self.master.matchup_set.get(stage=final, position=1)
        if sf2_winner is not None:
            fm.contestant1 = sf1_winner
            fm.contestant2 = sf2_winner
        fm.winner = final_winner
        fm.save(update_fields=["contestant1", "contestant2", "winner"])

    def test_potential_rank_differs_from_rank_by_potential_points(self):
        t1, t2, t3, t4 = self.teams
        self._set_master_partial(sf1_winner=t1)

        ub_a = self._submit("a", sf1=t1, sf2=t3, final_winner=t1)
        ub_b = self._submit("b", sf1=t1, sf2=t4, final_winner=t4)
        ub_c = self._submit("c", sf1=t2, sf2=t3, final_winner=t3)

        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        ub_a.refresh_from_db()
        ub_b.refresh_from_db()
        ub_c.refresh_from_db()

        by_potential = sorted(
            [ub_a, ub_b, ub_c],
            key=lambda ub: (ub.leaderboard_potential or 0, ub.user.username),
            reverse=True,
        )
        self.assertEqual(by_potential[0].user.username, "b")
        self.assertNotEqual(by_potential[0].id, ub_a.id)

        ranks = compute_potential_ranks_for_bracket(self.bracket)
        self.assertIsNotNone(ranks)
        self.assertEqual(ranks[ub_a.id], 1)

    def test_master_change_recomputes_potential_rank(self):
        t1, t2, t3, t4 = self.teams
        self._set_master_partial(sf1_winner=t1)
        ub = self._submit("solo", sf1=t1, sf2=t3, final_winner=t1)

        on_master_bracket_changed(self.bracket)
        ub.refresh_from_db()
        bundle = read_stored_leaderboard_scores(ub)
        self.assertEqual(bundle.potential_rank, 1)

        self._set_master_partial(sf1_winner=t1, sf2_winner=t3, final_winner=t1)
        on_master_bracket_changed(self.bracket)
        ub.refresh_from_db()
        bundle = read_stored_leaderboard_scores(ub)
        self.assertEqual(bundle.potential_rank, 1)

    def test_materialize_backfills_rank_when_scores_already_current(self):
        # Mirrors data confirmed before potential rank shipped: scores exist at
        # the current revision but the rank column is null. Materialize should
        # backfill it without requiring a master change.
        from brackets.utils.leaderboard_scoring import (
            materialize_leaderboard_scores_batch,
        )

        t1, t2, t3, t4 = self.teams
        self._set_master_partial(sf1_winner=t1)
        ub = self._submit("solo", sf1=t1, sf2=t3, final_winner=t1)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        # Simulate legacy rows: rank cleared, scores still current.
        UserBracket.objects.filter(pk=ub.pk).update(leaderboard_potential_rank=None)
        ub.refresh_from_db()
        self.assertIsNone(ub.leaderboard_potential_rank)

        result = materialize_leaderboard_scores_batch(self.bracket)
        self.assertEqual(result["remaining_count"], 0)
        ub.refresh_from_db()
        self.assertEqual(ub.leaderboard_potential_rank, 1)

    def test_live_mode_omits_potential_rank_from_leaderboard(self):
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "live-pot-rank",
            "Live Pot Rank",
            8,
            self.host,
        )
        for i in range(8):
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"G{i + 1}", seed=i + 1
            )
        bracket.metadata = set_group_results_mode_on_metadata(
            bracket.metadata, "live"
        )
        bracket.save(update_fields=["metadata"])
        challenge = BracketChallenge.objects.create(
            name="Live Pool",
            bracket=bracket,
            created_by=self.host,
            join_code="LIVEPRK1",
        )
        player = User.objects.create_user(username="live_viewer", password="x")
        ub = UserBracket.objects.create(
            user=player,
            bracket=bracket,
            challenge=challenge,
            submitted_at=timezone.now(),
            leaderboard_potential_rank=1,
        )
        refresh_all_submitted_leaderboard_scores_for_bracket(bracket)

        self.client.login(username="live_viewer", password="x")
        res = self.client.get(f"/brackets/api/challenges/{challenge.id}/leaderboard")
        self.assertEqual(res.status_code, 200)
        keys = [c["key"] for c in res.json()["columns"]]
        self.assertNotIn("potential_rank", keys)
        self.assertIsNone(res.json()["entries"][0]["potential_rank"])
        ub.refresh_from_db()
        self.assertEqual(ub.leaderboard_potential_rank, 1)

    def test_rank_not_computed_before_quarterfinals(self):
        """Potential rank stays off while the earliest incomplete stage has > 4 games."""
        from brackets.utils.potential_rank import (
            potential_rank_allowed_for_bracket,
            potential_rank_allowed_for_context,
        )

        t1, t2, t3, t4 = self.teams
        ub = self._submit("solo", sf1=t1, sf2=t3, final_winner=t1)
        # 4-team bracket: semis are the earliest incomplete stage (2 games) — allowed.
        self.assertTrue(potential_rank_allowed_for_bracket(self.bracket))
        result = compute_potential_ranks_for_bracket(self.bracket)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result[ub.id])

        scores = compute_potential_scores_for_bracket(self.bracket)
        self.assertIsNotNone(scores)
        self.assertIsNotNone(scores[ub.id])

        # 16-team group → knockout: first main round has 8 matchups (R16) — blocked.
        big = create_bracket_with_structure(
            "GROUP_KNOCKOUT",
            "pot-rank-gate-16",
            "Rank gate 16",
            16,
            self.host,
        )
        for i in range(16):
            BracketContestant.objects.create(
                bracket=big, name_override=f"B{i + 1}", seed=i + 1
            )
        big_master = big.get_master_bracket()
        ensure_knockout_structure_for_user_bracket(big_master)
        gp = {
            "A": {"1": 1, "2": 2, "3": 3, "4": 4},
            "B": {"1": 5, "2": 6, "3": 7, "4": 8},
            "C": {"1": 9, "2": 10, "3": 11, "4": 12},
            "D": {"1": 13, "2": 14, "3": 15, "4": 16},
        }
        big_master.metadata = {"group_positions": gp}
        big_master.save()
        sync_first_knockout_from_group_picks(big_master)
        first_ko = big.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        for m in big_master.matchup_set.filter(stage=first_ko):
            m.winner = None
            m.save(update_fields=["winner"])

        self.assertFalse(potential_rank_allowed_for_bracket(big))
        ctx = load_leaderboard_scoring_context(big)
        self.assertFalse(potential_rank_allowed_for_context(ctx))
        big_ub = UserBracket.objects.create(
            user=User.objects.create_user(username="bigplayer", password="x"),
            bracket=big,
            submitted_at=timezone.now(),
        )
        blocked = compute_potential_ranks_for_bracket(big)
        self.assertIsNotNone(blocked)
        self.assertIsNone(blocked[big_ub.id])

    def test_confirmed_mode_leaderboard_includes_potential_rank(self):
        t1, t2, t3, t4 = self.teams
        self._set_master_partial(sf1_winner=t1)
        self._submit("player_conf", sf1=t1, sf2=t3, final_winner=t1)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        self.client.login(username="player_conf", password="x")
        res = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}/leaderboard"
        )
        self.assertEqual(res.status_code, 200)
        cols = {c["key"]: c["name"] for c in res.json()["columns"]}
        self.assertIn("potential_rank", cols)
        self.assertEqual(cols["potential_rank"], "Potential Rank")
        # Points column is relabeled for clarity once rank is shown.
        self.assertEqual(cols["potential"], "Potential Pts")
        self.assertIsNotNone(res.json()["entries"][0]["potential_rank"])

    def test_potential_rank_column_hidden_until_gate_lifts(self):
        # Group -> knockout master with no group results yet: the first knockout
        # round is not seeded, so rank is not computable and the column is hidden.
        bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "gk-gate", "GK Gate", 8, self.host
        )
        for i in range(8):
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"GK{i + 1}", seed=i + 1
            )
        challenge = BracketChallenge.objects.create(
            name="GK Pool",
            bracket=bracket,
            created_by=self.host,
            join_code="GKGATE01",
        )
        player = User.objects.create_user(username="gk_viewer", password="x")
        UserBracket.objects.create(
            user=player,
            bracket=bracket,
            challenge=challenge,
            submitted_at=timezone.now(),
        )
        refresh_all_submitted_leaderboard_scores_for_bracket(bracket)

        self.client.login(username="gk_viewer", password="x")
        res = self.client.get(f"/brackets/api/challenges/{challenge.id}/leaderboard")
        self.assertEqual(res.status_code, 200)
        cols = {c["key"]: c["name"] for c in res.json()["columns"]}
        self.assertNotIn("potential_rank", cols)
        # Without the rank column, the points column keeps its plain label.
        self.assertEqual(cols["potential"], "Potential")
        self.assertIsNone(res.json()["entries"][0]["potential_rank"])


class PotentialRankBatchHelpersTests(TestCase):
    def _pairwise_competition_ranks(self, totals):
        import numpy as np

        batch_size, n_players = totals.shape
        ranks = np.empty((batch_size, n_players), dtype=np.int32)
        for b in range(batch_size):
            for p in range(n_players):
                ranks[b, p] = 1 + int(np.sum(totals[b] > totals[b, p]))
        return ranks

    def test_competition_ranks_batch_matches_pairwise_reference(self):
        import numpy as np

        from brackets.utils.potential_rank import competition_ranks_batch

        rng = np.random.default_rng(7)
        totals = rng.integers(0, 100, size=(64, 250)).astype(np.float64)
        expected = self._pairwise_competition_ranks(totals)
        actual = competition_ranks_batch(totals)
        np.testing.assert_array_equal(actual, expected)

    def test_competition_ranks_batch_handles_ties(self):
        import numpy as np

        from brackets.utils.potential_rank import competition_ranks_batch

        totals = np.array([[100.0, 100.0, 90.0, 80.0]], dtype=np.float64)
        ranks = competition_ranks_batch(totals)
        np.testing.assert_array_equal(ranks, np.array([[1, 1, 3, 4]], dtype=np.int32))

    def test_completion_batch_size_shrinks_with_player_count(self):
        from brackets.utils.potential_knockout import (
            MAX_BATCH_SIZE,
            completion_batch_size,
        )

        small_field = completion_batch_size(50, 4, 32)
        large_field = completion_batch_size(2000, 4, 32)
        self.assertGreater(small_field, large_field)
        self.assertLessEqual(small_field, MAX_BATCH_SIZE)
        self.assertLessEqual(large_field, MAX_BATCH_SIZE)
