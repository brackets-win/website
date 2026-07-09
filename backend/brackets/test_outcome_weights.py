"""Outcome weights for weighted challenge likelihood."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from brackets.models import BracketChallenge, BracketContestant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.challenge_outcomes import build_challenge_outcomes
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket
from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
from brackets.utils.outcome_weights import (
    build_effective_ratings,
    get_outcome_weights,
    merge_outcome_weights,
    set_outcome_weights_on_metadata,
    show_outcome_weights_for_bracket,
    validate_outcome_weights_payload,
    win_probability_from_rankings,
)
from brackets.utils.potential_rank import potential_rank_allowed_for_bracket

User = get_user_model()


class OutcomeWeightsTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "weights-se4",
            "Weights SE4",
            4,
            self.host,
        )
        self.challenge = BracketChallenge.objects.create(
            name="Pool",
            bracket=self.bracket,
            created_by=self.host,
            join_code="WEIGHTS1",
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

    def _set_master_partial(self, *, sf1_winner):
        semi, _final = self._ko_stages()
        t1, t2, t3, t4 = self.teams

        m1 = self.master.matchup_set.get(stage=semi, position=1)
        m1.contestant1, m1.contestant2, m1.winner = t1, t2, sf1_winner
        m1.save(update_fields=["contestant1", "contestant2", "winner"])

        m2 = self.master.matchup_set.get(stage=semi, position=2)
        m2.contestant1, m2.contestant2 = t3, t4
        m2.winner = None
        m2.save(update_fields=["contestant1", "contestant2", "winner"])

    def _submit(self, username, *, sf2, final_winner):
        user = User.objects.create_user(username=username, password="x")
        ub = UserBracket.objects.create(
            user=user,
            bracket=self.bracket,
            challenge=self.challenge,
            submitted_at=timezone.now(),
        )
        semi, final = self._ko_stages()
        ensure_knockout_structure_for_user_bracket(ub)
        t1, t2, t3, t4 = self.teams

        m1 = ub.matchup_set.get(stage=semi, position=1)
        m1.contestant1, m1.contestant2, m1.winner = t1, t2, t1
        m1.save(update_fields=["contestant1", "contestant2", "winner"])

        m2 = ub.matchup_set.get(stage=semi, position=2)
        m2.contestant1, m2.contestant2, m2.winner = t3, t4, sf2
        m2.save(update_fields=["contestant1", "contestant2", "winner"])

        fm = ub.matchup_set.get(stage=final, position=1)
        fm.contestant1, fm.contestant2, fm.winner = t1, sf2, final_winner
        fm.save(update_fields=["contestant1", "contestant2", "winner"])
        return ub

    def test_rank_formula_favors_better_rank(self):
        p = win_probability_from_rankings(1, 20)
        self.assertGreater(p, 0.5)
        self.assertLess(win_probability_from_rankings(20, 1), 0.5)

    def test_show_outcome_weights_when_potential_rank_allowed(self):
        t1, _, _, _ = self.teams
        self._set_master_partial(sf1_winner=t1)
        self.assertTrue(potential_rank_allowed_for_bracket(self.bracket))
        self.assertTrue(show_outcome_weights_for_bracket(self.bracket))

    def test_likelihood_differs_from_equal_weight_pct(self):
        t1, _, t3, t4 = self.teams
        self._set_master_partial(sf1_winner=t1)
        self._submit("heavy", sf2=t3, final_winner=t1)
        self._submit("light", sf2=t4, final_winner=t4)

        m2 = self.master.matchup_set.get(stage=self._ko_stages()[0], position=2)
        self.bracket.metadata = set_outcome_weights_on_metadata(
            self.bracket.metadata,
            team_rankings={team.id: i + 1 for i, team in enumerate(self.teams)},
            matchup_win_pct={m2.id: 90.0},
        )
        self.bracket.save(update_fields=["metadata"])

        payload = build_challenge_outcomes(self.challenge)
        self.assertIsNotNone(payload)
        odds_by_name = {
            row["entry"]["display_name"]: row for row in payload["winner_odds"]
        }
        self.assertIn("likelihood", odds_by_name["heavy"])
        self.assertIn("likelihood", odds_by_name["light"])
        self.assertGreater(
            odds_by_name["heavy"]["likelihood"],
            odds_by_name["heavy"]["pct"],
        )
        self.assertLess(
            odds_by_name["light"]["likelihood"],
            odds_by_name["light"]["pct"],
        )

    def test_validate_requires_rankings_for_current_teams(self):
        t1, _, _, _ = self.teams
        self._set_master_partial(sf1_winner=t1)
        ctx = load_leaderboard_scoring_context(self.bracket)
        m2 = self.master.matchup_set.get(stage=self._ko_stages()[0], position=2)

        error = validate_outcome_weights_payload(
            self.master,
            ctx,
            team_rankings={},
            matchup_win_pct={},
        )
        self.assertIsNotNone(error)

        error = validate_outcome_weights_payload(
            self.master,
            ctx,
            team_rankings={team.id: i + 1 for i, team in enumerate(self.teams)},
            matchup_win_pct={},
        )
        self.assertIsNone(error)

        error = validate_outcome_weights_payload(
            self.master,
            ctx,
            team_rankings={team.id: i + 1 for i, team in enumerate(self.teams)},
            matchup_win_pct={m2.id: 55.0},
        )
        self.assertIsNone(error)

    def test_merge_keeps_prior_round_odds_on_save(self):
        t1, _, t3, t4 = self.teams
        semi, final = self._ko_stages()
        self._set_master_partial(sf1_winner=t1)
        m2 = self.master.matchup_set.get(stage=semi, position=2)

        self.bracket.metadata = set_outcome_weights_on_metadata(
            self.bracket.metadata,
            team_rankings={team.id: i + 1 for i, team in enumerate(self.teams)},
            matchup_win_pct={m2.id: 70.0},
        )
        self.bracket.save(update_fields=["metadata"])

        m2.winner = t3
        m2.save(update_fields=["winner"])
        fm = self.master.matchup_set.get(stage=final, position=1)
        fm.contestant1, fm.contestant2 = t1, t3
        fm.save(update_fields=["contestant1", "contestant2"])

        ctx = load_leaderboard_scoring_context(self.bracket)
        existing = get_outcome_weights(self.bracket)
        merged = merge_outcome_weights(
            existing,
            team_rankings={t1.id: 1, t3.id: 3},
            matchup_win_pct={},
        )
        error = validate_outcome_weights_payload(
            self.master,
            ctx,
            team_rankings={t1.id: 1, t3.id: 3},
            matchup_win_pct={},
            existing=existing,
        )
        self.assertIsNone(error)
        self.assertEqual(merged.matchup_win_pct[m2.id], 70.0)

    def test_likelihood_uses_prior_round_odds_before_next_round_odds_exist(self):
        t1, _, t3, t4 = self.teams
        semi, final = self._ko_stages()
        self._set_master_partial(sf1_winner=t1)
        self._submit("fav", sf2=t3, final_winner=t1)
        self._submit("alt", sf2=t3, final_winner=t3)

        m2 = self.master.matchup_set.get(stage=semi, position=2)
        m2.winner = t3
        m2.save(update_fields=["winner"])
        fm = self.master.matchup_set.get(stage=final, position=1)
        fm.contestant1, fm.contestant2 = t1, t3
        fm.save(update_fields=["contestant1", "contestant2"])

        self.bracket.metadata = set_outcome_weights_on_metadata(
            self.bracket.metadata,
            team_rankings={t1.id: 1, t3.id: 8, t4.id: 20},
            matchup_win_pct={m2.id: 85.0},
        )
        self.bracket.save(update_fields=["metadata"])

        weights = get_outcome_weights(self.bracket)
        effective = build_effective_ratings(weights, self.master)
        self.assertNotEqual(effective[t3.id], effective[t4.id])

        payload = build_challenge_outcomes(self.challenge)
        odds_by_name = {
            row["entry"]["display_name"]: row for row in payload["winner_odds"]
        }
        self.assertIn("likelihood", odds_by_name["fav"])
        self.assertIn("likelihood", odds_by_name["alt"])

    def test_outcome_weights_api(self):
        t1, _, _, _ = self.teams
        self._set_master_partial(sf1_winner=t1)
        m2 = self.master.matchup_set.get(stage=self._ko_stages()[0], position=2)
        self.host.is_staff = True
        self.host.save(update_fields=["is_staff"])
        self.client.login(username="host", password="x")
        res = self.client.patch(
            f"/brackets/api/brackets/{self.bracket.id}/outcome-weights",
            data={
                "team_rankings": {
                    str(team.id): i + 1 for i, team in enumerate(self.teams)
                },
                "matchup_odds": {str(m2.id): 60.0},
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        meta = res.json()["bracket"]["metadata"]["outcome_weights"]
        self.assertEqual(meta["matchup_odds"][str(m2.id)], 60.0)
