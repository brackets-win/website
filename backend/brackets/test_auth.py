"""Authentication: case-insensitive login and username uniqueness."""

import json

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase

User = get_user_model()


class CaseInsensitiveLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(username="Mike", password="right-pass-123")

    def _login(self, username, password):
        return self.client.post(
            "/brackets/api/auth/login",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )

    def test_login_exact_case(self):
        res = self._login("Mike", "right-pass-123")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["username"], "Mike")

    def test_login_different_case(self):
        for typed in ("mike", "MIKE", "mIkE"):
            res = self._login(typed, "right-pass-123")
            self.assertEqual(res.status_code, 200, typed)
            self.assertEqual(res.json()["user"]["username"], "Mike")

    def test_login_surrounding_whitespace_trimmed(self):
        res = self._login("  mike  ", "right-pass-123")
        self.assertEqual(res.status_code, 200)

    def test_login_wrong_password_still_rejected(self):
        res = self._login("mike", "wrong-pass")
        self.assertEqual(res.status_code, 401)

    def test_login_unknown_user_rejected(self):
        res = self._login("nobody", "right-pass-123")
        self.assertEqual(res.status_code, 401)


class CaseInsensitiveRegistrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(username="Taken", password="pw-123-abc")

    def _register(self, username, password):
        return self.client.post(
            "/brackets/api/auth/register",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )

    def test_register_rejects_case_variant_username(self):
        res = self._register("taken", "new-pass-123abc")
        self.assertEqual(res.status_code, 409)
        self.assertFalse(User.objects.filter(username="taken").exists())


class UsernameUniquenessConstraintTests(TestCase):
    def test_db_blocks_case_variant_duplicate(self):
        User.objects.create_user(username="Alice", password="pw-123-abc")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(username="alice", password="pw-123-abc")
