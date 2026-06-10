"""Rename a bracket challenge entry by join code and current display name."""

from django.core.management.base import BaseCommand, CommandError

from django.conf import settings

from brackets.api.views import _normalize_display_name, _normalize_join_code
from brackets.models import BracketChallenge, UserBracket
from brackets.models.streak_challenge import StreakChallenge
from brackets.utils.challenge_entries import assert_display_name_available


class Command(BaseCommand):
    help = (
        "Rename a bracket challenge entry. "
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

        challenge = (
            BracketChallenge.objects.filter(join_code=join_code)
            .select_related("bracket")
            .first()
        )
        if challenge is None:
            streak = StreakChallenge.objects.filter(join_code=join_code).first()
            if streak is not None:
                raise CommandError(
                    f"Join code {join_code!r} is a streak challenge ({streak.name!r}), "
                    "not a bracket challenge. This command only renames bracket entries."
                )
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
                db_hint += "No bracket challenge has this join code."
            raise CommandError(f"No challenge found with join code {join_code!r}. {db_hint}")

        old_name = (options["old_name"] or "").strip()
        if not old_name:
            raise CommandError("old_name is required.")

        try:
            new_name = _normalize_display_name(options["new_name"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if old_name.casefold() == new_name.casefold():
            raise CommandError("New name must differ from the current name.")

        entries = UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            display_name__iexact=old_name,
        ).select_related("user")

        username = (options.get("username") or "").strip()
        if username:
            entries = entries.filter(user__username=username)

        count = entries.count()
        if count == 0:
            hint = f" (username={username!r})" if username else ""
            raise CommandError(
                f"No entry named {old_name!r} in challenge {challenge.name!r}{hint}."
            )
        if count > 1:
            owners = ", ".join(
                sorted({ub.user.username for ub in entries})
            )
            raise CommandError(
                f"Multiple entries named {old_name!r} ({owners}). "
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
                f"Renamed entry in {challenge.name!r} "
                f"({challenge.bracket.name}): "
                f"{previous!r} → {new_name!r} "
                f"(user={entry.user.username}, entry_id={entry.pk})"
            )
        )
