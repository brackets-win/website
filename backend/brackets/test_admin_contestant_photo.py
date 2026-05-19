"""Admin contestant photo upload (multipart PATCH)."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.test.client import BOUNDARY, encode_multipart

from brackets.models import Contestant, User

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001d90a2a0000000049454e44ae426082"
)


class AdminContestantPhotoTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username="admin",
            password="secret",
            is_staff=True,
        )
        self.contestant = Contestant.objects.create(
            identifier="brazil",
            name="Brazil",
            created_by=self.staff,
        )

    def test_patch_multipart_uploads_photo(self):
        self.client.force_login(self.staff)
        data = {
            "name": "Brazil",
            "description": "",
            "photo": SimpleUploadedFile("flag.png", PNG, content_type="image/png"),
        }
        body = encode_multipart(BOUNDARY, data)
        res = self.client.generic(
            "PATCH",
            f"/brackets/api/admin/contestants/{self.contestant.id}",
            body,
            content_type=f"multipart/form-data; boundary={BOUNDARY}",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()["contestant"]
        self.assertTrue(payload["photo_url"].startswith("/media/"))
        self.contestant.refresh_from_db()
        self.assertTrue(self.contestant.photo.name)
