"""Auth API tests."""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

User = get_user_model()


class AuthApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_register_creates_user_and_logs_in(self):
        res = self.client.post(
            "/brackets/api/auth/register",
            data=json.dumps(
                {"username": "newplayer", "password": "safe-pass-123"}
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        payload = res.json()
        self.assertEqual(payload["user"]["username"], "newplayer")
        self.assertFalse(payload["user"]["is_staff"])
        self.assertTrue(User.objects.filter(username="newplayer").exists())

        me = self.client.get("/brackets/api/auth/me")
        self.assertEqual(me.json()["user"]["username"], "newplayer")

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user(username="taken", password="x")
        res = self.client.post(
            "/brackets/api/auth/register",
            data=json.dumps({"username": "taken", "password": "safe-pass-123"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 409)

    def test_register_rejects_weak_password(self):
        res = self.client.post(
            "/brackets/api/auth/register",
            data=json.dumps({"username": "weak", "password": "123"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
