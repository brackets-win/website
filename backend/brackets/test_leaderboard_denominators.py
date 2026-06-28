"""Leaderboard PTS/% toggle denominators."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from brackets.models import BracketContestant, UserBracket
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.leaderboard_scoring import (
    compute_leaderboard_denominators,
    load_leaderboard_scoring_context,
)

User = get_user_model()


class LeaderboardDenominatorTests(TestCase):
    def _bracket(self, structure, ident, size):
        host = User.objects.create_user(username=f"h_{ident}", password="x")
        bracket = create_bracket_with_structure(
            structure, ident, ident.upper(), size, host
        )
        teams = [
            BracketContestant.objects.create(
                bracket=bracket, name_override=f"T{i + 1}", seed=i + 1
            )
            for i in range(size)
        ]
        return bracket, teams

    def test_no_master_results_dashes_total_and_stages(self):
        bracket, _ = self._bracket("GROUP_KNOCKOUT", "den-gk", 8)
        ctx = load_leaderboard_scoring_context(bracket)
        den = compute_leaderboard_denominators(ctx)

        # Nothing decided yet: total and every column denominator are 0, which
        # the UI renders as a dash in both PTS and % modes.
        self.assertEqual(den["total"], 0)
        self.assertTrue(den["columns"])
        self.assertTrue(all(v == 0 for v in den["columns"].values()))
        # The fully completed perfect bracket still has a positive max so the
        # Potential % column has a denominator.
        self.assertGreater(den["potential"], 0)

    def test_total_is_sum_of_column_denominators(self):
        bracket, teams = self._bracket("GROUP_KNOCKOUT", "den-sum", 8)
        master = UserBracket.objects.get(bracket=bracket, is_master=True)
        master.metadata = {
            "group_positions": {
                "A": {str(i + 1): teams[i].id for i in range(4)},
            }
        }
        master.save(update_fields=["metadata"])

        ctx = load_leaderboard_scoring_context(bracket)
        den = compute_leaderboard_denominators(ctx)

        self.assertEqual(den["total"], sum(den["columns"].values()))
        self.assertGreaterEqual(den["potential"], den["total"])

    def test_knockout_only_hidden_first_round_excluded(self):
        bracket, _ = self._bracket("SINGLE_ELIM", "den-ko", 8)
        first_ko = bracket.stages.order_by("order").first()
        ctx = load_leaderboard_scoring_context(bracket)
        den = compute_leaderboard_denominators(
            ctx, hidden_stage_id=first_ko.id
        )

        self.assertNotIn(f"stage:{first_ko.id}", den["columns"])
        # Potential still accounts for the seeded first round in its max.
        self.assertGreater(den["potential"], 0)
