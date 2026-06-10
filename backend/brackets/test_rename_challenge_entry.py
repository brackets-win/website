"""Management command: rename_challenge_entry."""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from brackets.models import (
    BracketChallenge,
    StreakChallenge,
    StreakCompetition,
    StreakParticipant,
    User,
    UserBracket,
)
from brackets.utils.bracket_factory import create_bracket_with_structure


class RenameChallengeEntryCommandTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(username="host", password="x")
        self.player = User.objects.create_user(username="guest", password="x")
        self.bracket = create_bracket_with_structure(
            "SINGLE_ELIM", "rename-cmd", "Cup", 4, self.host
        )
        self.bracket_challenge = BracketChallenge.objects.create(
            name="Bracket pool",
            bracket=self.bracket,
            created_by=self.host,
            join_code="BRCKT001",
        )
        self.streak_challenge = StreakChallenge.objects.create(
            name="Streak pool",
            streak_competition=StreakCompetition.objects.create(name="Props"),
            created_by=self.host,
            join_code="STREAK01",
        )

    def test_renames_bracket_entry(self):
        ub = UserBracket.objects.create(
            user=self.player,
            bracket=self.bracket,
            challenge=self.bracket_challenge,
            is_master=False,
            display_name="Alice",
        )
        call_command(
            "rename_challenge_entry",
            "BRCKT001",
            "Alice",
            "Alicia",
        )
        ub.refresh_from_db()
        self.assertEqual(ub.display_name, "Alicia")

    def test_renames_streak_entry(self):
        participant = StreakParticipant.objects.create(
            streak_challenge=self.streak_challenge,
            user=self.player,
            display_name="Connor Hubbard",
        )
        call_command(
            "rename_challenge_entry",
            "STREAK01",
            "Connor Hubbard",
            "Connor",
        )
        participant.refresh_from_db()
        self.assertEqual(participant.display_name, "Connor")

    def test_unknown_join_code(self):
        with self.assertRaises(CommandError):
            call_command(
                "rename_challenge_entry",
                "NOTFOUND",
                "Old",
                "New",
            )
