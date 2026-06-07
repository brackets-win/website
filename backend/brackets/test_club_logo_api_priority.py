"""Club logo API priority over uploaded/custom contestant images."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from brackets.models import Contestant, ContestantTag, User
from brackets.utils.contestant_images import club_logo_url, resolve_contestant_image_url

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001d90a2a0000000049454e44ae426082"
)


class ClubLogoApiPriorityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="clubs", password="x")
        self.club_tag = ContestantTag.objects.create(name="club")

    def _club(self, *, metadata: dict | None = None) -> Contestant:
        c = Contestant.objects.create(
            identifier="arsenal",
            name="Arsenal",
            created_by=self.user,
            metadata=metadata,
            image_url="https://example.com/custom.png",
        )
        c.tags.add(self.club_tag)
        c.photo.save(
            "club.png",
            SimpleUploadedFile("club.png", PNG, content_type="image/png"),
            save=True,
        )
        return c

    @patch("brackets.utils.contestant_images.club_logo_url")
    def test_resolve_uses_api_logo_before_uploaded_or_custom(self, mock_api: Mock):
        club = self._club(metadata={"thesportsdb_team_id": "133604"})
        mock_api.return_value = "https://cdn.example.com/badge.png"
        self.assertEqual(
            resolve_contestant_image_url(club),
            "https://cdn.example.com/badge.png",
        )

    @patch("brackets.utils.contestant_images.club_logo_url")
    def test_resolve_falls_back_when_api_has_no_logo(self, mock_api: Mock):
        club = self._club(metadata={"thesportsdb_team_id": "133604"})
        mock_api.return_value = None
        # Uploaded photo fallback still works when API has no image.
        resolved = resolve_contestant_image_url(club)
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertTrue(resolved.startswith("/media/contestants/photos/"))

    @patch("brackets.utils.contestant_images.urlopen")
    def test_club_logo_lookup_reads_thesportsdb_badge(self, mock_urlopen: Mock):
        club = self._club(metadata={"thesportsdb_team_id": "133604"})
        payload = {
            "teams": [
                {"idTeam": "133604", "strBadge": "https://r2.thesportsdb.com/badge.png"}
            ]
        }
        response = Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        logo = club_logo_url(club)
        self.assertEqual(logo, "https://r2.thesportsdb.com/badge.png")

    @patch("brackets.utils.contestant_images.urlopen")
    def test_club_logo_lookup_ignores_mismatched_team_payload(self, mock_urlopen: Mock):
        club = self._club(metadata={"thesportsdb_team_id": "133650"})
        payload = {
            "teams": [
                {"idTeam": "133604", "strBadge": "https://r2.thesportsdb.com/badge.png"}
            ]
        }
        response = Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        logo = club_logo_url(club)
        self.assertEqual(
            logo,
            "https://r2.thesportsdb.com/images/media/team/badge/tqo8ge1716960353.png",
        )

