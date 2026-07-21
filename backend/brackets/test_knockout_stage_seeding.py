"""Knockout stage seeding modes: standard, reseed, and randomize."""

from django.test import TestCase

from brackets.models import (
    BracketContestant,
    BracketStage,
    Contestant,
    KnockoutStage,
    Matchup,
    User,
)
from brackets.utils.bracket_factory import create_bracket_with_structure
from brackets.utils.knockout_stage_seeding import (
    pair_reseed,
    rng_for_stage_draw,
    sort_contestants_by_seed,
)
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket


class KnockoutStageSeedingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="koseed", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM",
            "ko-seed-8",
            "KO Seed 8",
            8,
            self.user,
        )
        self.ub = self.bracket.get_master_bracket()
        self.bcs = []
        for i in range(8):
            c = Contestant.objects.create(
                identifier=f"ko-seed-team-{i + 1}",
                name=f"Team {i + 1}",
                created_by=self.user,
            )
            self.bcs.append(
                BracketContestant.objects.create(
                    bracket=self.bracket, contestant=c, seed=i + 1
                )
            )
        ensure_knockout_structure_for_user_bracket(self.ub)
        self.ko_stages = list(
            self.bracket.stages.filter(
                stage_type=BracketStage.StageType.KNOCKOUT
            ).order_by("order")
        )
        self.r1 = self.ko_stages[0]
        self.r2 = self.ko_stages[1]
        self.r3 = self.ko_stages[2]

    def _matchup(self, stage, position: int) -> Matchup:
        return Matchup.objects.get(
            user_bracket=self.ub, stage=stage, position=position
        )

    def _set_r2_reseed(self):
        ks = KnockoutStage.objects.get(pk=self.r2.pk)
        ks.seeding_mode = KnockoutStage.SeedingMode.RESEED
        ks.save(update_fields=["seeding_mode"])

    def _set_r2_randomize(self):
        ks = KnockoutStage.objects.get(pk=self.r2.pk)
        ks.seeding_mode = KnockoutStage.SeedingMode.RANDOMIZE
        ks.save(update_fields=["seeding_mode"])

    def test_pair_reseed_orders_highest_vs_lowest(self):
        ordered = sort_contestants_by_seed(self.bcs[:4])
        pairs = pair_reseed(ordered)
        self.assertEqual(
            [(a.seed, b.seed) for a, b in pairs],
            [(1, 4), (2, 3)],
        )

    def test_standard_advances_by_tree_slot(self):
        m1 = self._matchup(self.r1, 1)
        m1.winner = m1.contestant1
        m1.save()
        r2 = self._matchup(self.r2, 1)
        self.assertEqual(r2.contestant1_id, m1.contestant1_id)
        self.assertIsNone(r2.contestant2_id)

    def test_reseed_waits_until_round_complete(self):
        self._set_r2_reseed()
        m1 = self._matchup(self.r1, 1)
        m1.winner = m1.contestant1
        m1.save()
        for pos in range(1, 3):
            r2 = self._matchup(self.r2, pos)
            self.assertIsNone(r2.contestant1_id)
            self.assertIsNone(r2.contestant2_id)

    def test_reseed_pairs_highest_vs_lowest_among_winners(self):
        self._set_r2_reseed()
        # Standard R1: 1v8, 4v5, 2v7, 3v6 — pick seeds 1,5,2,6
        winners_by_pos = {
            1: self.bcs[0],  # seed 1
            2: self.bcs[4],  # seed 5
            3: self.bcs[1],  # seed 2
            4: self.bcs[5],  # seed 6
        }
        for pos, winner in winners_by_pos.items():
            m = self._matchup(self.r1, pos)
            m.winner = winner
            m.save()

        r2_pairs = [
            (
                self._matchup(self.r2, pos).contestant1.seed,
                self._matchup(self.r2, pos).contestant2.seed,
            )
            for pos in range(1, 3)
        ]
        # Among seeds 1,2,5,6 → 1v6, 2v5
        self.assertEqual(r2_pairs, [(1, 6), (2, 5)])

    def test_reseed_clears_when_winner_cleared(self):
        self._set_r2_reseed()
        for pos in range(1, 5):
            m = self._matchup(self.r1, pos)
            m.winner = m.contestant1
            m.save()
        self.assertIsNotNone(self._matchup(self.r2, 1).contestant1_id)

        from brackets.utils.knockout_rebuild import clear_matchup_winner_and_downstream

        clear_matchup_winner_and_downstream(self._matchup(self.r1, 4))
        for pos in range(1, 3):
            r2 = self._matchup(self.r2, pos)
            self.assertIsNone(r2.contestant1_id)
            self.assertIsNone(r2.contestant2_id)

    def test_randomize_is_deterministic_for_same_winners(self):
        self._set_r2_randomize()
        for pos in range(1, 5):
            m = self._matchup(self.r1, pos)
            m.winner = m.contestant1
            m.save()

        first = [
            (
                self._matchup(self.r2, pos).contestant1_id,
                self._matchup(self.r2, pos).contestant2_id,
            )
            for pos in range(1, 3)
        ]

        # Clear and re-apply same winners — same draw.
        from brackets.utils.knockout_rebuild import clear_matchup_winner_and_downstream

        for pos in range(1, 5):
            clear_matchup_winner_and_downstream(self._matchup(self.r1, pos))
        for pos in range(1, 5):
            m = self._matchup(self.r1, pos)
            m.winner = m.contestant1
            m.save()

        second = [
            (
                self._matchup(self.r2, pos).contestant1_id,
                self._matchup(self.r2, pos).contestant2_id,
            )
            for pos in range(1, 3)
        ]
        self.assertEqual(first, second)

        # Sanity: draw matches helper RNG.
        winners = [self._matchup(self.r1, pos).winner for pos in range(1, 5)]
        rng = rng_for_stage_draw(
            self.ub.id, self.r2.id, [w.id for w in winners]
        )
        from brackets.utils.knockout_stage_seeding import pair_randomize

        expected = pair_randomize(winners, rng=rng)
        self.assertEqual(
            first,
            [(a.id, b.id) for a, b in expected],
        )
