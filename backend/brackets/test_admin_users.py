"""Admin user management and forced password change."""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

User = get_user_model()


class AdminUsersApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username="admin",
            password="staff-pass-123",
            is_staff=True,
        )
        self.player = User.objects.create_user(
            username="player",
            password="player-pass-123",
        )

    def test_list_users_requires_staff(self):
        self.client.force_login(self.player)
        res = self.client.get("/brackets/api/admin/users")
        self.assertEqual(res.status_code, 403)

    def test_list_users_returns_accounts(self):
        self.client.force_login(self.staff)
        res = self.client.get("/brackets/api/admin/users")
        self.assertEqual(res.status_code, 200)
        usernames = {row["username"] for row in res.json()["users"]}
        self.assertIn("admin", usernames)
        self.assertIn("player", usernames)

    def test_reset_password_sets_temp_and_forces_change(self):
        self.client.force_login(self.staff)
        res = self.client.post(
            f"/brackets/api/admin/users/{self.player.id}/reset-password"
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        temp = payload["temp_password"]
        self.assertTrue(payload["user"]["must_change_password"])

        self.player.refresh_from_db()
        self.assertTrue(self.player.must_change_password)
        self.assertTrue(self.player.check_password(temp))

        self.client.logout()
        login = self.client.post(
            "/brackets/api/auth/login",
            data=json.dumps({"username": "player", "password": temp}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["user"]["must_change_password"])

    def test_cannot_reset_own_password_via_admin(self):
        self.client.force_login(self.staff)
        res = self.client.post(
            f"/brackets/api/admin/users/{self.staff.id}/reset-password"
        )
        self.assertEqual(res.status_code, 400)

    def test_delete_user_requires_typed_resource_impact(self):
        self.client.force_login(self.staff)
        impact = self.client.get(
            f"/brackets/api/admin/delete-impact/user/{self.player.id}"
        )
        self.assertEqual(impact.status_code, 200)
        self.assertIn("related", impact.json())

    def test_delete_user(self):
        self.client.force_login(self.staff)
        res = self.client.delete(f"/brackets/api/admin/users/{self.player.id}")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(id=self.player.id).exists())

    def test_cannot_delete_self(self):
        self.client.force_login(self.staff)
        res = self.client.delete(f"/brackets/api/admin/users/{self.staff.id}")
        self.assertEqual(res.status_code, 400)


class AuthChangePasswordTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="player",
            password="temp-pass-123",
            must_change_password=True,
        )

    def test_forced_change_clears_flag(self):
        self.client.force_login(self.user)
        res = self.client.post(
            "/brackets/api/auth/change-password",
            data=json.dumps({"new_password": "new-safe-pass-456"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["user"]["must_change_password"])

        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password("new-safe-pass-456"))

    def test_voluntary_change_requires_current_password(self):
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        self.client.force_login(self.user)

        bad = self.client.post(
            "/brackets/api/auth/change-password",
            data=json.dumps({"new_password": "new-safe-pass-456"}),
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)

        ok = self.client.post(
            "/brackets/api/auth/change-password",
            data=json.dumps(
                {
                    "current_password": "temp-pass-123",
                    "new_password": "new-safe-pass-456",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)
