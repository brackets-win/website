"""Home-list tournament final summary for completed finals."""

from django.test import TestCase

from brackets.models import (
    BracketChallenge,
    KnockoutStage,
    Matchup,
    User,
    UserBracket,
)
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.challenge_types import TOURNAMENT
from brackets.utils.results_entry import merge_results_entry_into_metadata
from brackets.utils.tournament_final_summary import load_tournament_finals
from brackets.utils.tournament_teams import apply_tournament_teams


class TournamentFinalSummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="finalhost", password="x")

    def _make_tournament(self, *, knockout: str, n: int = 4):
        bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            f"se-final-{knockout}-{n}",
            "Final Card",
            n,
            self.user,
        )
        bracket.metadata = merge_results_entry_into_metadata(
            bracket.metadata,
            {"group": "standings", "knockout": knockout},
        )
        bracket.save(update_fields=["metadata"])
        teams = [{"name": f"T{i}", "seed": i} for i in range(1, n + 1)]
        apply_tournament_teams(bracket, teams)
        challenge = BracketChallenge.objects.create(
            name="Cup",
            bracket=bracket,
            created_by=self.user,
            instance_type=TOURNAMENT,
            is_public=True,
        )
        return challenge, bracket

    def test_winner_mode_returns_champion_without_scores(self):
        challenge, bracket = self._make_tournament(knockout="winner")
        master = UserBracket.objects.get(bracket=bracket, is_master=True)
        final_stage = KnockoutStage.objects.get(bracket=bracket, is_final=True)
        final = Matchup.objects.get(user_bracket=master, stage=final_stage)
        # Seed finalists + winner.
        semis = list(
            Matchup.objects.filter(
                user_bracket=master,
                stage__order=final_stage.order - 1,
            ).order_by("position")
        )
        self.assertEqual(len(semis), 2)
        for m in semis:
            self.assertIsNotNone(m.contestant1_id)
            m.winner_id = m.contestant1_id
            m.save(update_fields=["winner_id"])
        final.refresh_from_db()
        # Ensure finalists are populated the way the tree would.
        if final.contestant1_id is None:
            final.contestant1_id = semis[0].winner_id
        if final.contestant2_id is None:
            final.contestant2_id = semis[1].winner_id
        final.winner_id = final.contestant1_id
        final.save()

        payload = load_tournament_finals([challenge]).get(challenge.id)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["knockout_entry"], "winner")
        self.assertEqual(payload["winner_id"], final.winner_id)
        self.assertIsNone(payload["scores"])
        self.assertEqual(payload["contestant1"]["id"], final.contestant1_id)

    def test_score_mode_includes_totals(self):
        challenge, bracket = self._make_tournament(knockout="score")
        master = UserBracket.objects.get(bracket=bracket, is_master=True)
        final_stage = KnockoutStage.objects.get(bracket=bracket, is_final=True)
        final = Matchup.objects.get(user_bracket=master, stage=final_stage)
        semis = list(
            Matchup.objects.filter(
                user_bracket=master,
                stage__order=final_stage.order - 1,
            ).order_by("position")
        )
        for m in semis:
            m.winner_id = m.contestant1_id
            m.save(update_fields=["winner_id"])
        final.refresh_from_db()
        if final.contestant1_id is None:
            final.contestant1_id = semis[0].winner_id
        if final.contestant2_id is None:
            final.contestant2_id = semis[1].winner_id
        final.scores = {"legs": [[2, 1]]}
        final.winner_id = final.contestant1_id
        final.save()

        payload = load_tournament_finals([challenge]).get(challenge.id)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["knockout_entry"], "score")
        self.assertEqual(payload["scores"]["total1"], 2)
        self.assertEqual(payload["scores"]["total2"], 1)

    def test_incomplete_final_omitted(self):
        challenge, _bracket = self._make_tournament(knockout="winner")
        self.assertIsNone(load_tournament_finals([challenge]).get(challenge.id))
