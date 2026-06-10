"""Rename a challenge entry by join code and current display name."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from brackets.api.views import _normalize_display_name, _normalize_join_code
from brackets.models import BracketChallenge, UserBracket
from brackets.models.streak_challenge import StreakChallenge, StreakParticipant
from brackets.utils.challenge_entries import assert_display_name_available


class Command(BaseCommand):
    help = (
        "Rename a bracket or streak challenge entry. "
        "Finds the entry by join code and current display name, then sets a new name."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "join_code",
            help="Challenge join code (case-insensitive)",
        )
        parser.add_argument(
            "old_name",
            help="Current entry display name",
        )
        parser.add_argument(
            "new_name",
            help="New entry display name",
        )
        parser.add_argument(
            "--username",
            "-u",
            help="Disambiguate when multiple users share the same entry name",
        )

    def handle(self, *args, **options):
        join_code = _normalize_join_code(options["join_code"])
        if join_code is None:
            raise CommandError("Invalid join code.")

        old_name = (options["old_name"] or "").strip()
        if not old_name:
            raise CommandError("old_name is required.")

        try:
            new_name = _normalize_display_name(options["new_name"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if old_name.casefold() == new_name.casefold():
            raise CommandError("New name must differ from the current name.")

        username = (options.get("username") or "").strip()

        bracket_challenge = (
            BracketChallenge.objects.filter(join_code=join_code)
            .select_related("bracket")
            .first()
        )
        if bracket_challenge is not None:
            self._rename_bracket_entry(
                bracket_challenge, old_name, new_name, username
            )
            return

        streak_challenge = StreakChallenge.objects.filter(join_code=join_code).first()
        if streak_challenge is not None:
            self._rename_streak_entry(
                streak_challenge, old_name, new_name, username
            )
            return

        db = settings.DATABASES["default"]
        db_hint = (
            f"Connected to {db['ENGINE'].rsplit('.', 1)[-1]} "
            f"({db.get('NAME', 'default')}). "
        )
        if settings.DEBUG:
            db_hint += (
                "Local dev data only — production join codes are not here. "
                "Deploy this command, then run it on Fly: "
                "fly ssh console -a brackets-win"
            )
        else:
            db_hint += "No challenge has this join code."
        raise CommandError(f"No challenge found with join code {join_code!r}. {db_hint}")

    def _rename_bracket_entry(
        self,
        challenge: BracketChallenge,
        old_name: str,
        new_name: str,
        username: str,
    ) -> None:
        entries = UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            display_name__iexact=old_name,
        ).select_related("user")

        if username:
            entries = entries.filter(user__username=username)

        count = entries.count()
        if count == 0:
            hint = f" (username={username!r})" if username else ""
            raise CommandError(
                f"No bracket entry named {old_name!r} in {challenge.name!r}{hint}."
            )
        if count > 1:
            owners = ", ".join(sorted({ub.user.username for ub in entries}))
            raise CommandError(
                f"Multiple bracket entries named {old_name!r} ({owners}). "
                "Pass --username to pick one."
            )

        entry = entries.get()
        try:
            assert_display_name_available(
                challenge,
                entry.user,
                new_name,
                exclude_user_bracket_id=entry.pk,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        previous = entry.display_name
        entry.display_name = new_name
        entry.save(update_fields=["display_name"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Renamed bracket entry in {challenge.name!r} "
                f"({challenge.bracket.name}): "
                f"{previous!r} → {new_name!r} "
                f"(user={entry.user.username}, entry_id={entry.pk})"
            )
        )

    def _rename_streak_entry(
        self,
        challenge: StreakChallenge,
        old_name: str,
        new_name: str,
        username: str,
    ) -> None:
        entries = StreakParticipant.objects.filter(
            streak_challenge=challenge,
            display_name__iexact=old_name,
        ).select_related("user")

        if username:
            entries = entries.filter(user__username=username)

        count = entries.count()
        if count == 0:
            hint = f" (username={username!r})" if username else ""
            raise CommandError(
                f"No streak entry named {old_name!r} in {challenge.name!r}{hint}."
            )
        if count > 1:
            owners = ", ".join(sorted({p.user.username for p in entries}))
            raise CommandError(
                f"Multiple streak entries named {old_name!r} ({owners}). "
                "Pass --username to pick one."
            )

        entry = entries.get()
        previous = entry.display_name
        entry.display_name = new_name
        entry.save(update_fields=["display_name"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Renamed streak entry in {challenge.name!r}: "
                f"{previous!r} → {new_name!r} "
                f"(user={entry.user.username}, participant_id={entry.pk})"
            )
        )
