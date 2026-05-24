"""Knockout pick propagation when an earlier-round winner changes."""

from django.test import TestCase

from brackets.models import BracketContestant, BracketStage, Contestant, Matchup, User
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket


class KnockoutWinnerChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="koreb", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "ko-rebuild-8",
            "KO rebuild 8",
            8,
            self.user,
        )
        self.ub = self.bracket.get_master_bracket()
        for i in range(8):
            c = Contestant.objects.create(
                identifier=f"ko-rebuild-team-{i + 1}",
                name=f"Team {i + 1}",
                created_by=self.user,
            )
            BracketContestant.objects.create(
                bracket=self.bracket, contestant=c, seed=i + 1
            )
        ensure_knockout_structure_for_user_bracket(self.ub)
        self.ko_stages = list(
            self.bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT).order_by(
                "order"
            )
        )
        self.r1 = self.ko_stages[0]
        self.r2 = self.ko_stages[1]
        self.r3 = self.ko_stages[2]

    def _matchup(self, stage, position: int) -> Matchup:
        return Matchup.objects.get(
            user_bracket=self.ub, stage=stage, position=position
        )

    def test_changing_round1_winner_clears_stale_downstream_picks(self):
        """X through R1+R2; pick Y in R1 — R2 slot becomes Y, R3 must not keep X."""
        m1 = self._matchup(self.r1, 1)
        team_x = m1.contestant1
        team_y = m1.contestant2

        m1.winner = team_x
        m1.save()
        m2 = self._matchup(self.r2, 1)
        self.assertEqual(m2.contestant1_id, team_x.id)

        m2.winner = team_x
        m2.save()
        m3 = self._matchup(self.r3, 1)
        self.assertEqual(m3.contestant1_id, team_x.id)

        m1.winner = team_y
        m1.save()

        m2.refresh_from_db()
        m3.refresh_from_db()
        self.assertEqual(m2.contestant1_id, team_y.id)
        self.assertIsNone(m2.winner_id)
        self.assertIsNone(m3.contestant1_id)
        self.assertIsNone(m3.winner_id)

    def test_changing_one_branch_does_not_clear_other_branch_picks(self):
        """Swapping R1 game 1 winner must not undo an unrelated R2 winner."""
        m1 = self._matchup(self.r1, 1)
        m1b = self._matchup(self.r1, 2)
        team_x = m1.contestant1
        team_y = m1.contestant2
        team_z = m1b.contestant1

        m1.winner = team_x
        m1.save()
        m1b.winner = team_z
        m1b.save()

        r2a = self._matchup(self.r2, 1)
        r2a.winner = team_z
        r2a.save()

        m1.winner = team_y
        m1.save()

        r2a.refresh_from_db()
        self.assertEqual(r2a.contestant1_id, team_y.id)
        self.assertEqual(r2a.contestant2_id, team_z.id)
        self.assertEqual(r2a.winner_id, team_z.id)
