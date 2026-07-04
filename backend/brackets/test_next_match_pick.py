"""Next-match leaderboard column: who each entry wants to win the next game."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketChallenge, BracketContestant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import (
    ensure_knockout_matchup_shell,
    ensure_knockout_structure_for_user_bracket,
)
from brackets.utils.leaderboard_scoring import (
    refresh_all_submitted_leaderboard_scores_for_bracket,
    refresh_user_bracket_leaderboard_cache,
)
from brackets.utils.next_match import (
    get_next_match_matchup,
    set_next_match_on_metadata,
)
from brackets.utils.next_match_pick import (
    _assign_picks,
    _knockout_depths_by_entry,
    compute_next_match_picks_for_bracket,
    persist_next_match_picks_for_bracket,
)

User = get_user_model()


class AssignPicksTests(TestCase):
    def test_indifferent_entries_get_less_popular_contestant(self):
        pref = {1: "x", 2: "x", 3: "y", 4: None}
        out = _assign_picks(pref, x_id=10, y_id=20)
        # x is more popular (2 vs 1), so the indifferent entry gets y (20).
        self.assertEqual(out, {1: 10, 2: 10, 3: 20, 4: 20})

    def test_tie_in_popularity_leaves_indifferent_blank(self):
        pref = {1: "x", 2: "y", 3: None}
        out = _assign_picks(pref, x_id=10, y_id=20)
        self.assertEqual(out[3], None)

    def test_all_indifferent_is_blank(self):
        pref = {1: None, 2: None}
        out = _assign_picks(pref, x_id=10, y_id=20)
        self.assertEqual(out, {1: None, 2: None})


class KnockoutDepthTests(TestCase):
    """Depth follows knockout round reached only — group placement is ignored."""

    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.bracket = create_bracket_with_structure(
            "GROUP_KNOCKOUT", "next-match-gk", "Next Match GK", 8, self.host
        )
        self.teams = [
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(8)
        ]
        self.challenge = BracketChallenge.objects.create(
            name="Pool", bracket=self.bracket, created_by=self.host, join_code="GKNEXT01"
        )

    def _submit_with_groups(self, username, gp):
        user = User.objects.create_user(username=username, password="x")
        ub = UserBracket.objects.create(
            bracket=self.bracket,
            user=user,
            challenge=self.challenge,
            is_master=False,
            submitted_at=timezone.now(),
            metadata={"group_positions": gp},
        )
        ensure_knockout_matchup_shell(ub)
        return ub

    def test_same_round_different_group_placement_ties(self):
        t = self.teams
        # T1 finishes 1st in group A, T2 finishes 2nd — both advance to the first
        # knockout round, so they reached the same depth despite the placement gap.
        gp = {
            "A": {"1": t[0].id, "2": t[1].id, "3": t[2].id, "4": t[3].id},
            "B": {"1": t[4].id, "2": t[5].id, "3": t[6].id, "4": t[7].id},
        }
        ub = self._submit_with_groups("p1", gp)

        depths = _knockout_depths_by_entry(self.bracket, [ub], {t[0].id, t[1].id})
        self.assertEqual(depths[ub.id][t[0].id], depths[ub.id][t[1].id])


class NextMatchPickTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(
            username="host", password="x", is_staff=True
        )
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "next-match-se4",
            "Next Match SE4",
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
            join_code="NEXTMAT1",
        )
        self.master = self.bracket.get_master_bracket()
        self.teams = [
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(4)
        ]
        ensure_knockout_structure_for_user_bracket(self.master)
        # Master: SF1 decided (t1), SF2 (t3 vs t4) is the undecided "next match".
        self.t1, self.t2, self.t3, self.t4 = self.teams
        self._set_master_sf2_pending()

    def _ko_stages(self):
        return list(
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order")
        )

    def _set_master_sf2_pending(self):
        semi, final = self._ko_stages()
        m1 = self.master.matchup_set.get(stage=semi, position=1)
        m1.contestant1, m1.contestant2, m1.winner = self.t1, self.t2, self.t1
        m1.save(update_fields=["contestant1", "contestant2", "winner"])
        m2 = self.master.matchup_set.get(stage=semi, position=2)
        m2.contestant1, m2.contestant2, m2.winner = self.t3, self.t4, None
        m2.save(update_fields=["contestant1", "contestant2", "winner"])

    def _master_sf2(self):
        semi, _ = self._ko_stages()
        return self.master.matchup_set.get(stage=semi, position=2)

    def _submit(self, username, *, sf1, sf2, final_winner):
        semi, final = self._ko_stages()
        user = User.objects.create_user(username=username, password="x")
        ub = UserBracket.objects.create(
            user=user,
            bracket=self.bracket,
            challenge=self.challenge,
            submitted_at=timezone.now(),
        )
        ensure_knockout_structure_for_user_bracket(ub)
        m1 = ub.matchup_set.get(stage=semi, position=1)
        m1.contestant1, m1.contestant2, m1.winner = self.t1, self.t2, sf1
        m1.save(update_fields=["contestant1", "contestant2", "winner"])
        m2 = ub.matchup_set.get(stage=semi, position=2)
        m2.contestant1, m2.contestant2, m2.winner = self.t3, self.t4, sf2
        m2.save(update_fields=["contestant1", "contestant2", "winner"])
        fm = ub.matchup_set.get(stage=final, position=1)
        fm.contestant1, fm.contestant2, fm.winner = sf1, sf2, final_winner
        fm.save(update_fields=["contestant1", "contestant2", "winner"])
        return ub

    def _set_next_match(self, matchup_id):
        self.bracket.metadata = set_next_match_on_metadata(
            self.bracket.metadata, matchup_id
        )
        self.bracket.save(update_fields=["metadata"])

    def test_get_next_match_validates_matchup(self):
        sf2 = self._master_sf2()
        self._set_next_match(sf2.id)
        self.assertEqual(get_next_match_matchup(self.bracket).id, sf2.id)

        # Once it has a winner it is no longer an upcoming game.
        sf2.winner = self.t3
        sf2.save(update_fields=["winner"])
        self.assertIsNone(get_next_match_matchup(self.bracket))

    def test_rank_based_picks_reflect_who_each_entry_wants(self):
        ub_x = self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        ub_y = self._submit("y", sf1=self.t1, sf2=self.t4, final_winner=self.t4)
        self._set_next_match(self._master_sf2().id)

        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        ub_x.refresh_from_db()
        ub_y.refresh_from_db()
        # x's title hopes ride on t3 advancing; y's on t4.
        self.assertEqual(ub_x.leaderboard_next_match_pick_id, self.t3.id)
        self.assertEqual(ub_y.leaderboard_next_match_pick_id, self.t4.id)

    def test_submit_computes_next_match_pick_for_new_entry_only(self):
        ub_x = self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        self._set_next_match(self._master_sf2().id)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)
        ub_x.refresh_from_db()
        self.assertEqual(ub_x.leaderboard_next_match_pick_id, self.t3.id)

        ub_z = self._submit("z", sf1=self.t2, sf2=self.t4, final_winner=self.t4)
        refresh_user_bracket_leaderboard_cache(ub_z)

        ub_x.refresh_from_db()
        ub_z.refresh_from_db()
        self.assertEqual(ub_x.leaderboard_next_match_pick_id, self.t3.id)
        self.assertEqual(ub_z.leaderboard_next_match_pick_id, self.t4.id)

    def test_submit_skips_next_match_pick_when_column_inactive(self):
        ub = self._submit("solo", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        refresh_user_bracket_leaderboard_cache(ub)
        ub.refresh_from_db()
        self.assertIsNone(ub.leaderboard_next_match_pick_id)

    def test_picks_follow_knockout_depth(self):
        # Each entry wants whichever of the two next-match teams they took deeper
        # into the knockout rounds in their own bracket.
        ub_x = self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        ub_y = self._submit("y", sf1=self.t1, sf2=self.t4, final_winner=self.t4)
        self._set_next_match(self._master_sf2().id)

        picks = compute_next_match_picks_for_bracket(self.bracket)
        self.assertEqual(picks[ub_x.id], self.t3.id)
        self.assertEqual(picks[ub_y.id], self.t4.id)

    def test_clearing_next_match_clears_picks(self):
        ub_x = self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        self._submit("y", sf1=self.t1, sf2=self.t4, final_winner=self.t4)
        self._set_next_match(self._master_sf2().id)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)
        ub_x.refresh_from_db()
        self.assertIsNotNone(ub_x.leaderboard_next_match_pick_id)

        self._set_next_match(None)
        persist_next_match_picks_for_bracket(self.bracket)
        ub_x.refresh_from_db()
        self.assertIsNone(ub_x.leaderboard_next_match_pick_id)

    def test_leaderboard_exposes_next_match_column(self):
        self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        self._submit("y", sf1=self.t1, sf2=self.t4, final_winner=self.t4)
        self._set_next_match(self._master_sf2().id)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        self.client.login(username="x", password="x")
        res = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}/leaderboard"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        cols = {c["key"]: c["name"] for c in body["columns"]}
        self.assertEqual(cols.get("next_match"), "Next Match")
        by_name = {e["username"]: e for e in body["entries"]}
        self.assertEqual(
            by_name["x"]["next_match_pick"]["bracket_contestant_id"], self.t3.id
        )
        self.assertEqual(
            by_name["y"]["next_match_pick"]["bracket_contestant_id"], self.t4.id
        )

    def test_endpoint_sets_and_validates_next_match(self):
        self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        sf2 = self._master_sf2()

        self.client.login(username="host", password="x")
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/next-match",
            data=json.dumps({"matchup_id": sf2.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.bracket.refresh_from_db()
        self.assertEqual(get_next_match_matchup(self.bracket).id, sf2.id)

        # A decided matchup is rejected.
        semi, _ = self._ko_stages()
        sf1 = self.master.matchup_set.get(stage=semi, position=1)
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/next-match",
            data=json.dumps({"matchup_id": sf1.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

        # Clearing it works.
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/next-match",
            data=json.dumps({"matchup_id": None}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.bracket.refresh_from_db()
        self.assertIsNone(get_next_match_matchup(self.bracket))

    def test_endpoint_defers_compute_until_apply(self):
        from brackets.utils.next_match import is_next_match_pending

        ub_x = self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        ub_y = self._submit("y", sf1=self.t1, sf2=self.t4, final_winner=self.t4)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)
        sf2 = self._master_sf2()

        # Setting the next match flags pending but does NOT compute picks inline.
        self.client.login(username="host", password="x")
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/next-match",
            data=json.dumps({"matchup_id": sf2.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.bracket.refresh_from_db()
        self.assertTrue(is_next_match_pending(self.bracket))
        ub_x.refresh_from_db()
        ub_y.refresh_from_db()
        self.assertIsNone(ub_x.leaderboard_next_match_pick_id)
        self.assertIsNone(ub_y.leaderboard_next_match_pick_id)

        # The master entry advertises a pending recompute (drives the Apply UI).
        master_res = self.client.get(
            f"/brackets/api/user-brackets/{self.master.id}"
        )
        self.assertTrue(
            master_res.json()["user_bracket"]["leaderboard_scores_pending"]
        )

        # Applying (materialize) computes the picks and clears the flag, without
        # needing any scores to be stale.
        res = self.client.post(
            f"/brackets/api/brackets/{self.bracket.id}/materialize-scores"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["remaining_count"], 0)
        self.assertFalse(res.json()["leaderboard_scores_pending"])
        self.bracket.refresh_from_db()
        self.assertFalse(is_next_match_pending(self.bracket))
        ub_x.refresh_from_db()
        ub_y.refresh_from_db()
        self.assertEqual(ub_x.leaderboard_next_match_pick_id, self.t3.id)
        self.assertEqual(ub_y.leaderboard_next_match_pick_id, self.t4.id)

    def test_clearing_next_match_takes_effect_without_apply(self):
        from brackets.utils.next_match import is_next_match_pending

        ub_x = self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        self._submit("y", sf1=self.t1, sf2=self.t4, final_winner=self.t4)
        self._set_next_match(self._master_sf2().id)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)
        ub_x.refresh_from_db()
        self.assertIsNotNone(ub_x.leaderboard_next_match_pick_id)

        self.client.login(username="host", password="x")
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/next-match",
            data=json.dumps({"matchup_id": None}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.bracket.refresh_from_db()
        self.assertFalse(is_next_match_pending(self.bracket))
        ub_x.refresh_from_db()
        self.assertIsNone(ub_x.leaderboard_next_match_pick_id)

    def test_setting_winner_on_next_match_clears_it(self):
        from brackets.utils.next_match import is_next_match_pending

        ub_x = self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        self._submit("y", sf1=self.t1, sf2=self.t4, final_winner=self.t4)
        self._set_next_match(self._master_sf2().id)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)
        ub_x.refresh_from_db()
        self.assertIsNotNone(ub_x.leaderboard_next_match_pick_id)

        # Admin sets the result of the very game that is the next match.
        sf2 = self._master_sf2()
        self.client.login(username="host", password="x")
        res = self.client.patch(
            f"/brackets/api/matchups/{sf2.id}",
            data=json.dumps({"winner_id": self.t3.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        # No game is the next match anymore: pointer, flag, and picks all clear.
        self.bracket.refresh_from_db()
        self.assertIsNone(get_next_match_matchup(self.bracket))
        self.assertNotIn(
            "next_match_matchup_id", self.bracket.metadata
        )
        self.assertFalse(is_next_match_pending(self.bracket))
        ub_x.refresh_from_db()
        self.assertIsNone(ub_x.leaderboard_next_match_pick_id)

    def test_setting_winner_on_other_match_keeps_next_match(self):
        self._submit("x", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        self._submit("y", sf1=self.t1, sf2=self.t4, final_winner=self.t4)
        sf2 = self._master_sf2()
        self._set_next_match(sf2.id)

        # Decide an unrelated game (the already-played SF1): next match stays.
        semi, _ = self._ko_stages()
        sf1 = self.master.matchup_set.get(stage=semi, position=1)
        self.client.login(username="host", password="x")
        res = self.client.patch(
            f"/brackets/api/matchups/{sf1.id}",
            data=json.dumps({"winner_id": self.t1.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.bracket.refresh_from_db()
        self.assertEqual(get_next_match_matchup(self.bracket).id, sf2.id)

    def test_endpoint_forbidden_for_non_admin(self):
        self._submit("player", sf1=self.t1, sf2=self.t3, final_winner=self.t3)
        sf2 = self._master_sf2()
        self.client.login(username="player", password="x")
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/next-match",
            data=json.dumps({"matchup_id": sf2.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)


class NextMatchFuturePreferenceTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(
            username="host-future", password="x", is_staff=True
        )
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "next-match-se8",
            "Next Match SE8",
            8,
            self.host,
            structure_config={
                "points_champion": 10,
                "knockout": {"points_per_correct_pick": 1},
            },
        )
        self.challenge = BracketChallenge.objects.create(
            name="Pool Future",
            bracket=self.bracket,
            created_by=self.host,
            join_code="NEXTMAT8",
        )
        self.master = self.bracket.get_master_bracket()
        self.teams = [
            BracketContestant.objects.create(
                bracket=self.bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(8)
        ]
        ensure_knockout_structure_for_user_bracket(self.master)
        (
            self.t1,
            self.t2,
            self.t3,
            self.t4,
            self.t5,
            self.t6,
            self.t7,
            self.t8,
        ) = self.teams
        self._set_master_sf1_pending()

    def _ko_stages(self):
        return list(
            self.bracket.stages.filter(stage_type="KNOCKOUT").order_by("order")
        )

    def _set_master_sf1_pending(self):
        quarter, semi, _final = self._ko_stages()
        for position, left, right, winner in [
            (1, self.t1, self.t2, self.t1),
            (2, self.t3, self.t4, self.t3),
            (3, self.t5, self.t6, self.t5),
            (4, self.t7, self.t8, self.t7),
        ]:
            match = self.master.matchup_set.get(stage=quarter, position=position)
            match.contestant1 = left
            match.contestant2 = right
            match.winner = winner
            match.save(update_fields=["contestant1", "contestant2", "winner"])
        sf1 = self.master.matchup_set.get(stage=semi, position=1)
        sf1.winner = None
        sf1.save(update_fields=["winner"])

    def _master_sf1(self):
        _quarter, semi, _final = self._ko_stages()
        return self.master.matchup_set.get(stage=semi, position=1)

    def _set_next_match(self, matchup_id):
        self.bracket.metadata = set_next_match_on_metadata(
            self.bracket.metadata, matchup_id
        )
        self.bracket.save(update_fields=["metadata"])

    def _submit(
        self,
        username,
        *,
        qf1,
        qf2,
        sf1,
        challenge=None,
        qf3=None,
        qf4=None,
        sf2=None,
        final_winner=None,
    ):
        quarter, semi, final = self._ko_stages()
        qf3 = qf3 or self.t5
        qf4 = qf4 or self.t7
        sf2 = sf2 or qf3
        final_winner = final_winner or sf2
        user = User.objects.create_user(username=username, password="x")
        ub = UserBracket.objects.create(
            user=user,
            bracket=self.bracket,
            challenge=challenge or self.challenge,
            submitted_at=timezone.now(),
        )
        ensure_knockout_structure_for_user_bracket(ub)
        for position, left, right, winner in [
            (1, self.t1, self.t2, qf1),
            (2, self.t3, self.t4, qf2),
            (3, self.t5, self.t6, qf3),
            (4, self.t7, self.t8, qf4),
        ]:
            match = ub.matchup_set.get(stage=quarter, position=position)
            match.contestant1 = left
            match.contestant2 = right
            match.winner = winner
            match.save(update_fields=["contestant1", "contestant2", "winner"])
        sf1_match = ub.matchup_set.get(stage=semi, position=1)
        sf1_match.contestant1 = qf1
        sf1_match.contestant2 = qf2
        sf1_match.winner = sf1
        sf1_match.save(update_fields=["contestant1", "contestant2", "winner"])
        sf2_match = ub.matchup_set.get(stage=semi, position=2)
        sf2_match.contestant1 = qf3
        sf2_match.contestant2 = qf4
        sf2_match.winner = sf2
        sf2_match.save(update_fields=["contestant1", "contestant2", "winner"])
        final_match = ub.matchup_set.get(stage=final, position=1)
        final_match.contestant1 = sf1
        final_match.contestant2 = sf2
        final_match.winner = final_winner
        final_match.save(update_fields=["contestant1", "contestant2", "winner"])
        return ub

    def test_current_round_result_does_not_create_preference(self):
        # One entry still has T1 alive beyond the semifinal, so indifferent
        # entries should inherit the less-popular side (T3).
        ub_future_t1 = self._submit(
            "future-t1",
            qf1=self.t1,
            qf2=self.t3,
            sf1=self.t1,
            final_winner=self.t5,
        )
        # T1 loses in the current semifinal and T3 was already out in quarters,
        # so neither team can earn more after this stage for this entry.
        ub_indifferent = self._submit(
            "indifferent",
            qf1=self.t1,
            qf2=self.t4,
            sf1=self.t4,
            final_winner=self.t5,
        )
        self._set_next_match(self._master_sf1().id)

        picks = compute_next_match_picks_for_bracket(self.bracket)
        self.assertEqual(picks[ub_future_t1.id], self.t1.id)
        self.assertEqual(picks[ub_indifferent.id], self.t3.id)

    def test_next_match_popularity_does_not_leak_across_challenges(self):
        other_challenge = BracketChallenge.objects.create(
            name="Other Pool",
            bracket=self.bracket,
            created_by=self.host,
            join_code="NEXTMAT9",
        )
        ub_a = self._submit(
            "pool-a",
            challenge=self.challenge,
            qf1=self.t2,
            qf2=self.t4,
            sf1=self.t4,
            final_winner=self.t5,
        )
        ub_b = self._submit(
            "pool-b",
            challenge=self.challenge,
            qf1=self.t2,
            qf2=self.t4,
            sf1=self.t4,
            final_winner=self.t5,
        )
        ub_other = self._submit(
            "other-pool",
            challenge=other_challenge,
            qf1=self.t1,
            qf2=self.t3,
            sf1=self.t1,
            final_winner=self.t5,
        )
        self._set_next_match(self._master_sf1().id)

        persist_next_match_picks_for_bracket(self.bracket)
        ub_a.refresh_from_db()
        ub_b.refresh_from_db()
        ub_other.refresh_from_db()

        self.assertIsNone(ub_a.leaderboard_next_match_pick_id)
        self.assertIsNone(ub_b.leaderboard_next_match_pick_id)
        self.assertEqual(ub_other.leaderboard_next_match_pick_id, self.t1.id)
