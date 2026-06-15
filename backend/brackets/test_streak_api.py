"""API tests for streak challenges."""

import json
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
    StreakQuestionChoice,
)

User = get_user_model()


class StreakCompetitionAdminApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username="admin", password="x", is_staff=True
        )
        self.competition = StreakCompetition.objects.create(name="World Cup Props")

    def test_staff_can_patch_competition_name(self):
        self.client.force_login(self.staff)
        res = self.client.patch(
            f"/brackets/api/streak-competitions/{self.competition.id}",
            data=json.dumps({"name": "WC Props"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.name, "WC Props")

    def test_staff_can_upload_competition_image(self):
        self.client.force_login(self.staff)
        image = SimpleUploadedFile(
            "cup.png",
            BytesIO(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
            ).getvalue(),
            content_type="image/png",
        )
        res = self.client.post(
            "/brackets/api/streak-competitions",
            data={"name": "With image", "image": image},
        )
        self.assertEqual(res.status_code, 201)
        payload = res.json()["streak_competition"]
        self.assertTrue(payload["image_url"])
        competition = StreakCompetition.objects.get(pk=payload["id"])
        self.assertTrue(competition.image.name.endswith(".png"))

    def test_staff_can_delete_competition_without_challenges(self):
        self.client.force_login(self.staff)
        pk = self.competition.pk
        res = self.client.delete(f"/brackets/api/streak-competitions/{pk}")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(StreakCompetition.objects.filter(pk=pk).exists())

    def test_cannot_delete_competition_with_challenges(self):
        creator = User.objects.create_user(username="host", password="x")
        StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=creator,
            is_public=True,
        )
        self.client.force_login(self.staff)
        res = self.client.delete(
            f"/brackets/api/streak-competitions/{self.competition.id}"
        )
        self.assertEqual(res.status_code, 409)
        self.assertTrue(
            StreakCompetition.objects.filter(pk=self.competition.pk).exists()
        )

    def test_staff_can_create_question_with_choices(self):
        self.client.force_login(self.staff)
        res = self.client.post(
            f"/brackets/api/streak-competitions/{self.competition.id}/questions",
            data=json.dumps(
                {
                    "text": "Who wins?",
                    "closes_at": "2030-01-01T12:00:00-05:00",
                    "choices": ["Argentina", "Brazil"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        payload = res.json()["question"]
        self.assertEqual(len(payload["choices"]), 2)
        self.assertEqual(payload["choices"][0]["label"], "Argentina")

    def test_questions_reorder_by_close_time(self):
        self.client.force_login(self.staff)
        later = self.client.post(
            f"/brackets/api/streak-competitions/{self.competition.id}/questions",
            data=json.dumps(
                {
                    "text": "Later",
                    "closes_at": "2030-06-01T12:00:00-05:00",
                    "choices": ["A", "B"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(later.status_code, 201)
        earlier = self.client.post(
            f"/brackets/api/streak-competitions/{self.competition.id}/questions",
            data=json.dumps(
                {
                    "text": "Earlier",
                    "closes_at": "2030-01-01T12:00:00-05:00",
                    "choices": ["A", "B"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(earlier.status_code, 201)

        detail = self.client.get(
            f"/brackets/api/streak-competitions/{self.competition.id}"
        )
        self.assertEqual(detail.status_code, 200)
        texts = [q["text"] for q in detail.json()["questions"]]
        self.assertEqual(texts, ["Earlier", "Later"])
        orders = list(
            StreakQuestion.objects.filter(
                streak_competition=self.competition
            ).order_by("closes_at", "id").values_list("order", flat=True)
        )
        self.assertEqual(orders, [1, 2])

    def test_staff_can_update_question_choices(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Who wins?",
            closes_at=timezone.now() + timezone.timedelta(days=1),
            order=1,
        )
        a = StreakQuestionChoice.objects.create(
            question=question, label="Argentina", order=1
        )
        b = StreakQuestionChoice.objects.create(
            question=question, label="Brazil", order=2
        )
        self.client.force_login(self.staff)
        patch_res = self.client.patch(
            f"/brackets/api/streak-questions/{question.id}",
            data=json.dumps(
                {
                    "choices": [
                        {"id": a.id, "label": "Argentina"},
                        {"id": b.id, "label": "Uruguay"},
                        {"label": "Chile"},
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_res.status_code, 200)
        payload = patch_res.json()["question"]
        self.assertEqual(len(payload["choices"]), 3)
        labels = [c["label"] for c in payload["choices"]]
        self.assertEqual(labels, ["Argentina", "Uruguay", "Chile"])
        question.refresh_from_db()
        self.assertEqual(
            list(question.choices.order_by("order").values_list("label", flat=True)),
            ["Argentina", "Uruguay", "Chile"],
        )

    def test_staff_can_update_and_delete_question(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Old text",
            closes_at=timezone.now() + timezone.timedelta(days=1),
            order=1,
        )
        StreakQuestionChoice.objects.create(
            question=question, label="A", order=1
        )
        StreakQuestionChoice.objects.create(
            question=question, label="B", order=2
        )
        self.client.force_login(self.staff)
        patch_res = self.client.patch(
            f"/brackets/api/streak-questions/{question.id}",
            data=json.dumps(
                {
                    "text": "New text",
                    "closes_at": "2030-06-15T20:00:00Z",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_res.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(question.text, "New text")

        delete_res = self.client.delete(
            f"/brackets/api/streak-questions/{question.id}"
        )
        self.assertEqual(delete_res.status_code, 200)
        self.assertFalse(StreakQuestion.objects.filter(pk=question.pk).exists())

    def test_staff_can_change_resolved_answer(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Winner?",
            closes_at=timezone.now() - timezone.timedelta(hours=1),
            order=1,
        )
        a = StreakQuestionChoice.objects.create(
            question=question, label="A", order=1
        )
        b = StreakQuestionChoice.objects.create(
            question=question, label="B", order=2
        )
        self.client.force_login(self.staff)
        first = self.client.post(
            f"/brackets/api/streak-questions/{question.id}/resolve",
            data=json.dumps({"correct_choice_id": a.id}),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)
        question.refresh_from_db()
        first_resolved_at = question.resolved_at

        second = self.client.post(
            f"/brackets/api/streak-questions/{question.id}/resolve",
            data=json.dumps({"correct_choice_id": b.id}),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(question.correct_choice_id, b.id)
        self.assertEqual(question.resolved_at, first_resolved_at)

    def test_staff_can_clear_resolved_answer(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Winner?",
            closes_at=timezone.now() - timezone.timedelta(hours=1),
            order=1,
        )
        a = StreakQuestionChoice.objects.create(
            question=question, label="A", order=1
        )
        StreakQuestionChoice.objects.create(question=question, label="B", order=2)
        self.client.force_login(self.staff)
        resolve_res = self.client.post(
            f"/brackets/api/streak-questions/{question.id}/resolve",
            data=json.dumps({"correct_choice_id": a.id}),
            content_type="application/json",
        )
        self.assertEqual(resolve_res.status_code, 200)

        clear_res = self.client.post(
            f"/brackets/api/streak-questions/{question.id}/resolve",
            data=json.dumps({"correct_choice_id": None}),
            content_type="application/json",
        )
        self.assertEqual(clear_res.status_code, 200)
        question.refresh_from_db()
        self.assertIsNone(question.correct_choice_id)
        self.assertIsNone(question.resolved_at)

    def test_staff_can_resolve_past_deadline_question(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Will it rain?",
            closes_at=timezone.now() - timezone.timedelta(hours=1),
            order=1,
        )
        yes = StreakQuestionChoice.objects.create(
            question=question, label="Yes", order=1
        )
        StreakQuestionChoice.objects.create(question=question, label="No", order=2)
        self.client.force_login(self.staff)
        res = self.client.post(
            f"/brackets/api/streak-questions/{question.id}/resolve",
            data=json.dumps({"correct_choice_id": yes.id}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(question.correct_choice_id, yes.id)
        self.assertIsNotNone(question.resolved_at)

    def test_admin_question_detail_includes_pick_count(self):
        creator = User.objects.create_user(username="host", password="x")
        player = User.objects.create_user(username="player", password="x")
        challenge_a = StreakChallenge.objects.create(
            name="Pool A",
            streak_competition=self.competition,
            created_by=creator,
            is_public=True,
        )
        challenge_b = StreakChallenge.objects.create(
            name="Pool B",
            streak_competition=self.competition,
            created_by=creator,
            is_public=True,
        )
        picked = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Picked",
            closes_at=timezone.now() + timezone.timedelta(days=1),
            order=1,
        )
        unpicked = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Unpicked",
            closes_at=timezone.now() + timezone.timedelta(days=2),
            order=2,
        )
        choice_a = StreakQuestionChoice.objects.create(
            question=picked, label="A", order=1
        )
        StreakQuestionChoice.objects.create(question=picked, label="B", order=2)
        StreakQuestionChoice.objects.create(question=unpicked, label="A", order=1)
        StreakQuestionChoice.objects.create(question=unpicked, label="B", order=2)
        StreakPick.objects.create(
            streak_challenge=challenge_a,
            question=picked,
            user=player,
            choice=choice_a,
        )
        StreakPick.objects.create(
            streak_challenge=challenge_b,
            question=picked,
            user=creator,
            choice=choice_a,
        )

        self.client.force_login(self.staff)
        res = self.client.get(
            f"/brackets/api/streak-competitions/{self.competition.id}"
        )
        self.assertEqual(res.status_code, 200)
        by_text = {q["text"]: q for q in res.json()["questions"]}
        self.assertEqual(by_text["Picked"]["pick_count"], 2)
        self.assertEqual(by_text["Unpicked"]["pick_count"], 0)


class StreakQuestionPickPctTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="player", password="x")
        self.other = User.objects.create_user(username="other", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.user,
            is_public=True,
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.user
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.other
        )

    def test_resolved_question_includes_pick_pct_per_choice(self):
        question = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Winner?",
            closes_at=timezone.now() - timezone.timedelta(hours=1),
            order=1,
        )
        yes = StreakQuestionChoice.objects.create(
            question=question, label="Yes", order=1
        )
        no = StreakQuestionChoice.objects.create(question=question, label="No", order=2)
        question.correct_choice = yes
        question.resolved_at = timezone.now()
        question.save(update_fields=["correct_choice", "resolved_at"])
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=question,
            user=self.user,
            choice=yes,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=question,
            user=self.other,
            choice=no,
        )
        self.client.force_login(self.user)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 200)
        payload = next(
            q for q in res.json()["questions"] if q["id"] == question.id
        )
        by_label = {c["label"]: c for c in payload["choices"]}
        self.assertEqual(by_label["Yes"]["pick_pct"], 50)
        self.assertEqual(by_label["Yes"]["pick_count"], 1)
        self.assertEqual(by_label["No"]["pick_pct"], 50)
        self.assertEqual(by_label["No"]["pick_count"], 1)


class StreakParticipantPicksApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.viewer = User.objects.create_user(username="viewer", password="x")
        self.other = User.objects.create_user(username="other", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.viewer,
            is_public=True,
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.viewer
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.other
        )

    def test_player_picks_only_include_resolved_questions(self):
        resolved = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Resolved Q",
            closes_at=timezone.now() - timezone.timedelta(hours=2),
            order=1,
        )
        yes = StreakQuestionChoice.objects.create(
            question=resolved, label="Yes", order=1
        )
        StreakQuestionChoice.objects.create(question=resolved, label="No", order=2)
        resolved.correct_choice = yes
        resolved.resolved_at = timezone.now()
        resolved.save(update_fields=["correct_choice", "resolved_at"])

        open_q = StreakQuestion.objects.create(
            streak_competition=self.competition,
            text="Open Q",
            closes_at=timezone.now() + timezone.timedelta(days=1),
            order=2,
        )
        a = StreakQuestionChoice.objects.create(question=open_q, label="A", order=1)
        StreakQuestionChoice.objects.create(question=open_q, label="B", order=2)

        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=resolved,
            user=self.other,
            choice=yes,
        )
        StreakPick.objects.create(
            streak_challenge=self.challenge,
            question=open_q,
            user=self.other,
            choice=a,
        )

        self.client.force_login(self.viewer)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/players/{self.other.id}/picks"
        )
        self.assertEqual(res.status_code, 200)
        picks = res.json()["picks"]
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["text"], "Resolved Q")
        self.assertEqual(len(picks[0]["choices"]), 2)
        self.assertEqual(picks[0]["pick_choice_id"], yes.id)
        self.assertEqual(picks[0]["correct_choice_id"], yes.id)
        self.assertTrue(picks[0]["is_correct"])


class StreakLeaderboardApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = User.objects.create_user(username="host", password="x")
        self.competition = StreakCompetition.objects.create(name="Cup")
        self.challenge = StreakChallenge.objects.create(
            name="Pool",
            streak_competition=self.competition,
            created_by=self.host,
            is_public=True,
        )
        StreakParticipant.objects.create(streak_challenge=self.challenge, user=self.host)
        join_names = {
            "Keaton": "K-Team",
            "coley2007": "Coley",
            "trady_baylor": "Trady",
            "jfigueroa17": "Jose",
        }
        for username, display_name in join_names.items():
            user = User.objects.create_user(username=username, password="x")
            StreakParticipant.objects.create(
                streak_challenge=self.challenge,
                user=user,
                display_name=display_name,
            )

    def test_ungraded_players_share_rank_one_and_sort_alphabetically(self):
        self.client.force_login(self.host)
        res = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/leaderboard"
        )
        self.assertEqual(res.status_code, 200)
        entries = res.json()["entries"]
        self.assertEqual(len(entries), 5)
        player_entries = [entry for entry in entries if entry["username"] != "host"]
        ranks = [entry["rank"] for entry in player_entries]
        self.assertEqual(ranks, [1, 1, 1, 1])
        names = [entry["display_name"] for entry in player_entries]
        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertNotIn("coley2007", names)

    def test_join_stores_display_name_on_leaderboard(self):
        user = User.objects.create_user(username="newbie", password="x")
        self.client.force_login(user)
        res = self.client.post(
            "/brackets/api/streak-challenges/join",
            data=json.dumps(
                {
                    "streak_challenge_id": self.challenge.id,
                    "display_name": "Pool Name",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        board = self.client.get(
            f"/brackets/api/streak-challenges/{self.challenge.id}/leaderboard"
        )
        names = [entry["display_name"] for entry in board.json()["entries"]]
        self.assertIn("Pool Name", names)


class StreakChallengeDeleteApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.creator = User.objects.create_user(username="host", password="x")
        self.joiner = User.objects.create_user(username="guest", password="x")
        self.competition = StreakCompetition.objects.create(name="Props")
        self.challenge = StreakChallenge.objects.create(
            name="Friends pool",
            streak_competition=self.competition,
            created_by=self.creator,
            is_public=False,
            join_code="STREAK01",
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.creator
        )
        StreakParticipant.objects.create(
            streak_challenge=self.challenge, user=self.joiner
        )

    def test_creator_can_delete_streak_challenge(self):
        self.client.force_login(self.creator)
        res = self.client.delete(
            f"/brackets/api/streak-challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            StreakChallenge.objects.filter(pk=self.challenge.pk).exists()
        )

    def test_non_creator_cannot_delete_streak_challenge(self):
        self.client.force_login(self.joiner)
        res = self.client.delete(
            f"/brackets/api/streak-challenges/{self.challenge.id}"
        )
        self.assertEqual(res.status_code, 403)
        self.assertTrue(
            StreakChallenge.objects.filter(pk=self.challenge.pk).exists()
        )
