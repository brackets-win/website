"""Tournament placement draw (random / random_balanced) and GK capacity."""

import json
import random
from unittest import mock

from django.test import Client, TestCase

from brackets.models import BracketContestant, Matchup, User
from brackets.utils.group_knockout_fill import get_knockout_fill_method
from brackets.utils.tournament_placement import compute_draw_seeds, supported_pot_counts
from brackets.utils.tournament_teams import tournament_team_capacity


class TournamentPlacementUnitTests(TestCase):
    def test_supported_pot_counts(self):
        self.assertEqual(supported_pot_counts(16), [2, 4, 8])
        self.assertEqual(supported_pot_counts(8), [2, 4])
        self.assertEqual(supported_pot_counts(4), [2])

    def test_random_balanced_one_from_each_pot_per_group(self):
        teams = []
        for pot in range(1, 5):
            for i in range(4):
                teams.append({"name": f"P{pot}T{i}", "pot": pot})
        with mock.patch("brackets.utils.tournament_placement.random.shuffle", new=lambda x: x):
            out = compute_draw_seeds(
                mode="random_balanced",
                teams=teams,
                structure="GROUP_KNOCKOUT",
                number_of_groups=4,
                teams_per_group=4,
            )
        # Contiguous seeds: group A = 1..4, etc. Each group should have pots 1-4.
        by_group = [out[i : i + 4] for i in range(0, 16, 4)]
        for chunk in by_group:
            pots = {name[1] for name in (t["name"] for t in chunk)}
            self.assertEqual(pots, {"1", "2", "3", "4"})


class TournamentGroupKnockoutTeamsApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="gkhost", password="x")
        self.client.force_login(self.host)

    def _create_gk_tournament(self, size: int = 8):
        res = self.client.post(
            "/brackets/api/challenges",
            data=json.dumps(
                {
                    "name": "GK Cup",
                    "instance_type": "TOURNAMENT",
                    "is_private": True,
                    "bracket_setup": {
                        "structure": "GROUP_KNOCKOUT",
                        "identifier": f"gk-teams-{size}",
                        "bracket_name": "GK Cup",
                        "number_of_contestants": size,
                        "structure_config": {
                            "group_stage": {
                                "number_of_groups": size // 4,
                                "contestants_qualifying_per_group": 2,
                            },
                            "knockout": {
                                "metadata": {"knockout_fill_method": "standard"}
                            },
                        },
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()["challenge"]

    def test_capacity_is_full_roster_not_ko_field(self):
        ch = self._create_gk_tournament(8)
        from brackets.models import Bracket

        bracket = Bracket.objects.get(pk=ch["bracket_id"])
        self.assertEqual(tournament_team_capacity(bracket), 8)
        res = self.client.get(f"/brackets/api/challenges/{ch['id']}/teams")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["team_count"], 8)
        self.assertEqual(data["structure"], "GROUP_KNOCKOUT")
        self.assertEqual(data["number_of_groups"], 2)
        self.assertEqual(data["teams_per_group"], 4)

        first_ko = (
            bracket.stages.filter(stage_type="KNOCKOUT").order_by("order").first()
        )
        self.assertEqual(first_ko.number_of_contestants, 4)
        self.assertEqual(
            get_knockout_fill_method(first_ko, bracket),
            "standard",
        )

    def test_draw_random_balanced_saves_seeds(self):
        ch = self._create_gk_tournament(8)
        teams = []
        for pot in (1, 2):
            for i in range(4):
                teams.append({"name": f"P{pot}-{i}", "pot": pot})
        with mock.patch.object(random, "shuffle", side_effect=lambda x: None):
            res = self.client.post(
                f"/brackets/api/challenges/{ch['id']}/teams/draw",
                data=json.dumps({"mode": "random_balanced", "teams": teams}),
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 200, res.content)
        saved = res.json()["teams"]
        self.assertEqual(len(saved), 8)
        seeds = [t["seed"] for t in saved]
        self.assertEqual(sorted(seeds), list(range(1, 9)))
        self.assertEqual(
            BracketContestant.objects.filter(bracket_id=ch["bracket_id"]).count(),
            8,
        )
        # Empty KO shell (no first-round contestants yet)
        master_id = ch["master_user_bracket_id"]
        first_round = Matchup.objects.filter(
            user_bracket_id=master_id,
            stage__order=2,
        )
        self.assertTrue(first_round.exists())
        self.assertTrue(
            all(m.contestant1_id is None and m.contestant2_id is None for m in first_round)
        )
