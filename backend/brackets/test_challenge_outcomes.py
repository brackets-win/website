"""Challenge outcomes — winners per possible master top-four finish."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketChallenge, BracketContestant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.challenge_outcomes import (
    build_challenge_outcomes,
    get_challenge_outcomes,
)
from brackets.utils.challenge_stats import (
    CHALLENGE_OUTCOMES_CACHE_KEY,
    bump_challenge_stats_master_revision,
    bump_challenge_stats_revision,
    get_challenge_stats_master_revision,
    get_challenge_stats_revision,
)
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket
from brackets.utils.leaderboard_scoring import refresh_all_submitted_leaderboard_scores_for_bracket

User = get_user_model()


class ChallengeOutcomesTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "outcomes-se4",
            "Outcomes SE4",
            4,
            self.host,
        )
        self.challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=self.bracket,
            created_by=self.host,
            join_code="OUTCOMES1",
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
        semi, final = self._ko_stages()
        ensure_knockout_structure_for_user_bracket(ub)
        t1, t2, t3, t4 = self.teams

        m1 = ub.matchup_set.get(stage=semi, position=1)
        m1.contestant1, m1.contestant2, m1.winner = t1, t2, sf1
        m1.save(update_fields=["contestant1", "contestant2", "winner"])

        m2 = ub.matchup_set.get(stage=semi, position=2)
        m2.contestant1, m2.contestant2, m2.winner = t3, t4, sf2
        m2.save(update_fields=["contestant1", "contestant2", "winner"])

        fm = ub.matchup_set.get(stage=final, position=1)
        fm.contestant1, fm.contestant2, fm.winner = sf1, sf2, final_winner
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

    def _all_winners(self, payload):
        winners: set[str] = set()

        def walk(nodes):
            for node in nodes:
                if "winners" in node:
                    winners.update(node["winners"])
                elif "children" in node:
                    walk(node["children"])

        walk(payload["tree"])
        return winners

    def test_outcomes_lists_winners_per_top_four_finish(self):
        t1, t2, t3, t4 = self.teams
        self._set_master_partial(sf1_winner=t1)
        self._submit("winner", sf1=t1, sf2=t3, final_winner=t1)
        self._submit("runner", sf1=t1, sf2=t4, final_winner=t4)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        payload = build_challenge_outcomes(self.challenge)
        self.assertIsNotNone(payload)
        self.assertTrue(payload["tree"])
        winners = self._all_winners(payload)
        self.assertIn("winner", winners)

    def test_outcomes_api_requires_submit(self):
        t1, _, t3, _ = self.teams
        self._set_master_partial(sf1_winner=t1)
        viewer = User.objects.create_user(username="viewer", password="x")
        self.client.login(username="viewer", password="x")
        res = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}/outcomes"
        )
        self.assertEqual(res.status_code, 403)

        ub = UserBracket.objects.create(
            user=viewer,
            bracket=self.bracket,
            challenge=self.challenge,
            submitted_at=timezone.now(),
        )
        self._fill_user_bracket(ub, sf1=t1, sf2=t3, final_winner=t1)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)
        res = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}/outcomes"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("tree", res.json())
        body = res.json()
        self.assertIn("total_outcomes", body)
        self.assertIn("winner_odds", body)

    def test_winner_odds_count_outcomes_per_entry(self):
        t1, t2, t3, t4 = self.teams
        self._set_master_partial(sf1_winner=t1)
        self._submit("alice", sf1=t1, sf2=t3, final_winner=t1)
        self._submit("bob", sf1=t1, sf2=t4, final_winner=t4)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        payload = build_challenge_outcomes(self.challenge)
        self.assertIsNotNone(payload)
        self.assertGreater(payload["total_outcomes"], 0)
        odds_by_name = {row["name"]: row for row in payload["winner_odds"]}
        self.assertTrue(odds_by_name)
        total = payload["total_outcomes"]
        for row in payload["winner_odds"]:
            self.assertEqual(row["pct"], round(100.0 * row["outcome_count"] / total, 1))

    def test_outcomes_are_cached_on_first_read(self):
        t1, _, t3, _ = self.teams
        self._set_master_partial(sf1_winner=t1)
        self._submit("cached", sf1=t1, sf2=t3, final_winner=t1)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        get_challenge_outcomes(self.challenge)
        self.challenge.refresh_from_db()
        cache = self.challenge.metadata.get(CHALLENGE_OUTCOMES_CACHE_KEY)
        self.assertIsInstance(cache, dict)
        self.assertEqual(
            cache["entries_revision"],
            get_challenge_stats_revision(self.challenge),
        )
        self.assertEqual(
            cache["master_revision"],
            get_challenge_stats_master_revision(self.challenge),
        )
        self.assertIn("payload", cache)

    def test_entry_bump_invalidates_outcomes_cache(self):
        t1, _, t3, _ = self.teams
        self._set_master_partial(sf1_winner=t1)
        self._submit("cache1", sf1=t1, sf2=t3, final_winner=t1)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        get_challenge_outcomes(self.challenge)
        bump_challenge_stats_revision(self.challenge)
        self.challenge.refresh_from_db()
        self.assertIsNone(self.challenge.metadata.get(CHALLENGE_OUTCOMES_CACHE_KEY))

    def test_master_bump_invalidates_outcomes_cache(self):
        t1, _, t3, _ = self.teams
        self._set_master_partial(sf1_winner=t1)
        self._submit("cache2", sf1=t1, sf2=t3, final_winner=t1)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        get_challenge_outcomes(self.challenge)
        bump_challenge_stats_master_revision(self.challenge)
        self.challenge.refresh_from_db()
        self.assertIsNone(self.challenge.metadata.get(CHALLENGE_OUTCOMES_CACHE_KEY))

    def test_leaderboard_potential_rank_before_potential_points(self):
        t1, _, t3, _ = self.teams
        self._set_master_partial(sf1_winner=t1)
        self._submit("cols", sf1=t1, sf2=t3, final_winner=t1)
        refresh_all_submitted_leaderboard_scores_for_bracket(self.bracket)

        self.client.login(username="cols", password="x")
        res = self.client.get(
            f"/brackets/api/challenges/{self.challenge.id}/leaderboard"
        )
        keys = [c["key"] for c in res.json()["columns"]]
        self.assertEqual(
            keys.index("potential_rank"),
            keys.index("potential") - 1,
        )
