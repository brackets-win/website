"""Tournament host team roster API."""

import json
from unittest import mock

from django.test import Client, TestCase

from brackets.models import BracketContestant, Matchup, User
from brackets.utils.tournament_teams import apply_tournament_teams, tournament_teams_public


class TournamentTeamsApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="x")
        self.client.force_login(self.host)

    def _create_tournament(self, size: int = 4):
        res = self.client.post(
            "/brackets/api/challenges",
            data=json.dumps(
                {
                    "name": "Cup",
                    "instance_type": "TOURNAMENT",
                    "bracket_setup": {
                        "structure": "SINGLE_ELIM",
                        "identifier": f"teams-test-{size}",
                        "bracket_name": "Cup",
                        "number_of_contestants": size,
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        return res.json()["challenge"]

    def test_get_teams_empty(self):
        ch = self._create_tournament(4)
        res = self.client.get(f"/brackets/api/challenges/{ch['id']}/teams")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["team_count"], 4)
        self.assertEqual(data["teams"], [])

    def test_put_teams_seeds_bracket(self):
        ch = self._create_tournament(4)
        master_id = ch["master_user_bracket_id"]
        res = self.client.put(
            f"/brackets/api/challenges/{ch['id']}/teams",
            data=json.dumps(
                {
                    "teams": [
                        {"name": "Alpha"},
                        {"name": "Bravo"},
                        {"name": "Charlie"},
                        {"name": "Delta"},
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()["teams"]
        names = [t["name"] for t in payload]
        self.assertEqual(names, ["Alpha", "Bravo", "Charlie", "Delta"])
        self.assertTrue(all(t.get("contestant_id") for t in payload))
        self.assertEqual(
            BracketContestant.objects.filter(
                bracket_id=ch["bracket_id"], contestant__isnull=False
            ).count(),
            4,
        )
        first_round = Matchup.objects.filter(
            user_bracket_id=master_id,
            stage__order=1,
        )
        self.assertEqual(first_round.count(), 2)
        self.assertTrue(
            all(m.contestant1_id and m.contestant2_id for m in first_round)
        )

    def test_challenge_summary_teams_configured(self):
        ch = self._create_tournament(4)
        detail = self.client.get(f"/brackets/api/challenges/{ch['id']}")
        self.assertFalse(detail.json()["challenge"]["teams_configured"])
        self.client.put(
            f"/brackets/api/challenges/{ch['id']}/teams",
            data=json.dumps(
                {
                    "teams": [
                        {"name": "A"},
                        {"name": "B"},
                        {"name": "C"},
                        {"name": "D"},
                    ]
                }
            ),
            content_type="application/json",
        )
        detail = self.client.get(f"/brackets/api/challenges/{ch['id']}")
        self.assertTrue(detail.json()["challenge"]["teams_configured"])

    def test_apply_tournament_teams_blocks_after_results(self):
        ch = self._create_tournament(4)
        bracket_id = ch["bracket_id"]
        from brackets.models import Bracket

        bracket = Bracket.objects.get(pk=bracket_id)
        apply_tournament_teams(
            bracket,
            [{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
        )
        master_id = ch["master_user_bracket_id"]
        m = Matchup.objects.filter(user_bracket_id=master_id).first()
        m.winner_id = m.contestant1_id
        m.save(update_fields=["winner_id"])
        with self.assertRaises(ValueError):
            apply_tournament_teams(
                bracket,
                [{"name": "1"}, {"name": "2"}, {"name": "3"}, {"name": "4"}],
            )

    def test_non_host_forbidden(self):
        ch = self._create_tournament(4)
        other = User.objects.create_user(username="other", password="x")
        self.client.force_login(other)
        res = self.client.put(
            f"/brackets/api/challenges/{ch['id']}/teams",
            data=json.dumps({"teams": []}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

    def test_team_catalog_create_and_assign(self):
        ch = self._create_tournament(4)
        create = self.client.post(
            f"/brackets/api/challenges/{ch['id']}/team-catalog",
            data=json.dumps({"name": "Lions"}),
            content_type="application/json",
        )
        self.assertEqual(create.status_code, 201)
        cid = create.json()["contestant"]["id"]
        catalog = self.client.get(
            f"/brackets/api/challenges/{ch['id']}/team-catalog"
        )
        self.assertEqual(catalog.status_code, 200)
        self.assertTrue(
            any(c["id"] == cid for c in catalog.json()["contestants"])
        )

        others = []
        for name in ("Tigers", "Bears", "Sharks"):
            r = self.client.post(
                f"/brackets/api/challenges/{ch['id']}/team-catalog",
                data=json.dumps({"name": name}),
                content_type="application/json",
            )
            self.assertEqual(r.status_code, 201)
            others.append(r.json()["contestant"])

        res = self.client.put(
            f"/brackets/api/challenges/{ch['id']}/teams",
            data=json.dumps(
                {
                    "teams": [
                        {"contestant_id": cid, "name": "Lions"},
                        {"contestant_id": others[0]["id"], "name": "Tigers"},
                        {"contestant_id": others[1]["id"], "name": "Bears"},
                        {"contestant_id": others[2]["id"], "name": "Sharks"},
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            [t["contestant_id"] for t in res.json()["teams"]],
            [cid, others[0]["id"], others[1]["id"], others[2]["id"]],
        )

    def test_start_tournament_locks_teams(self):
        ch = self._create_tournament(4)
        self.client.put(
            f"/brackets/api/challenges/{ch['id']}/teams",
            data=json.dumps(
                {
                    "teams": [
                        {"name": "A"},
                        {"name": "B"},
                        {"name": "C"},
                        {"name": "D"},
                    ]
                }
            ),
            content_type="application/json",
        )
        start = self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200)
        self.assertTrue(start.json()["tournament_started"])
        detail = self.client.get(f"/brackets/api/challenges/{ch['id']}")
        self.assertTrue(detail.json()["challenge"]["tournament_started"])
        blocked = self.client.put(
            f"/brackets/api/challenges/{ch['id']}/teams",
            data=json.dumps(
                {
                    "teams": [
                        {"name": "W"},
                        {"name": "X"},
                        {"name": "Y"},
                        {"name": "Z"},
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 400)

    def test_start_after_draw_with_byes(self):
        """Bye auto-winners must not block Start after a non-power-of-2 draw."""
        ch = self._create_tournament(6)
        teams = [
            {"name": f"T{i}", "pot": 1 if i <= 2 else 2} for i in range(1, 7)
        ]
        draw = self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/draw",
            data=json.dumps({"mode": "random_balanced", "teams": teams}),
            content_type="application/json",
        )
        self.assertEqual(draw.status_code, 200, draw.content)
        start = self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/start",
            data=json.dumps({"mode": "random_balanced", "teams": teams}),
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200, start.content)
        self.assertTrue(start.json()["tournament_started"])

    def test_redraw_reshuffles_from_saved_pots(self):
        ch = self._create_tournament(4)
        teams = [
            {"name": "P1A", "pot": 1},
            {"name": "P1B", "pot": 1},
            {"name": "P2A", "pot": 2},
            {"name": "P2B", "pot": 2},
        ]
        # Deterministic first draw (leave pot order as submitted).
        with mock.patch(
            "brackets.utils.tournament_placement.random.shuffle",
            side_effect=lambda x: None,
        ):
            draw = self.client.post(
                f"/brackets/api/challenges/{ch['id']}/teams/draw",
                data=json.dumps({"mode": "random_balanced", "teams": teams}),
                content_type="application/json",
            )
        self.assertEqual(draw.status_code, 200, draw.content)
        first_seeds = {
            t["name"]: t["seed"] for t in draw.json()["teams"]
        }

        start = self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200, start.content)
        self.assertTrue(start.json()["tournament_started"])

        detail = self.client.get(f"/brackets/api/challenges/{ch['id']}")
        self.assertTrue(detail.json()["challenge"]["tournament_can_redraw"])

        # Different deterministic shuffle on redraw.
        with mock.patch(
            "brackets.utils.tournament_placement.random.shuffle",
            side_effect=lambda x: x.reverse(),
        ):
            redraw = self.client.post(
                f"/brackets/api/challenges/{ch['id']}/teams/redraw",
                data=json.dumps({}),
                content_type="application/json",
            )
        self.assertEqual(redraw.status_code, 200, redraw.content)
        self.assertTrue(redraw.json()["tournament_started"])
        self.assertTrue(redraw.json()["tournament_can_redraw"])
        second_seeds = {
            t["name"]: t["seed"] for t in redraw.json()["teams"]
        }
        self.assertEqual(set(second_seeds), set(first_seeds))
        # Same roster, new placement from same pots.
        self.assertNotEqual(second_seeds, first_seeds)

        # Still locked — cannot manually replace teams.
        blocked = self.client.put(
            f"/brackets/api/challenges/{ch['id']}/teams",
            data=json.dumps(
                {
                    "teams": [
                        {"name": "W"},
                        {"name": "X"},
                        {"name": "Y"},
                        {"name": "Z"},
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 400)

    def test_redraw_blocked_without_draw_config(self):
        ch = self._create_tournament(4)
        self.client.put(
            f"/brackets/api/challenges/{ch['id']}/teams",
            data=json.dumps(
                {
                    "teams": [
                        {"name": "A"},
                        {"name": "B"},
                        {"name": "C"},
                        {"name": "D"},
                    ]
                }
            ),
            content_type="application/json",
        )
        self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        detail = self.client.get(f"/brackets/api/challenges/{ch['id']}")
        self.assertFalse(detail.json()["challenge"]["tournament_can_redraw"])
        redraw = self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/redraw",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(redraw.status_code, 400)

    def test_redraw_blocked_after_results(self):
        ch = self._create_tournament(4)
        teams = [
            {"name": "P1A", "pot": 1},
            {"name": "P1B", "pot": 1},
            {"name": "P2A", "pot": 2},
            {"name": "P2B", "pot": 2},
        ]
        self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/draw",
            data=json.dumps({"mode": "random_balanced", "teams": teams}),
            content_type="application/json",
        )
        self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        from brackets.models import Bracket, Matchup

        bracket = Bracket.objects.get(pk=ch["bracket_id"])
        master = bracket.get_master_bracket()
        m = (
            Matchup.objects.filter(
                user_bracket=master,
                contestant1_id__isnull=False,
                contestant2_id__isnull=False,
            )
            .order_by("id")
            .first()
        )
        self.assertIsNotNone(m)
        m.winner_id = m.contestant1_id
        m.save(update_fields=["winner_id"])

        detail = self.client.get(f"/brackets/api/challenges/{ch['id']}")
        self.assertFalse(detail.json()["challenge"]["tournament_can_redraw"])

        redraw = self.client.post(
            f"/brackets/api/challenges/{ch['id']}/teams/redraw",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(redraw.status_code, 400)
        still = self.client.get(f"/brackets/api/challenges/{ch['id']}")
        self.assertTrue(still.json()["challenge"]["tournament_started"])
        self.assertFalse(still.json()["challenge"]["tournament_can_redraw"])

