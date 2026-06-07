"""Grant in-app admin access (is_staff) to existing users by username."""

from django.core.management.base import BaseCommand, CommandError

from brackets.models import User


class Command(BaseCommand):
    help = (
        "Set is_staff=True for the given usernames (must already exist). "
        "Staff users see the Admin tab and can manage streak competitions, etc."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "usernames",
            nargs="+",
            help="Usernames to promote (case-sensitive, must match login name)",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Remove staff status instead of granting it",
        )

    def handle(self, *args, **options):
        usernames = [u.strip() for u in options["usernames"] if u.strip()]
        if not usernames:
            raise CommandError("Provide at least one username.")

        grant = not options["revoke"]
        missing: list[str] = []
        updated: list[str] = []

        for name in usernames:
            user = User.objects.filter(username=name).first()
            if user is None:
                missing.append(name)
                continue
            if user.is_staff == grant:
                self.stdout.write(f"  {name}: already {'staff' if grant else 'non-staff'}")
                continue
            user.is_staff = grant
            user.save(update_fields=["is_staff"])
            updated.append(name)

        if missing:
            raise CommandError(
                "No account for: "
                + ", ".join(missing)
                + ". They must register (or sign in once) before you can promote them."
            )

        verb = "Granted staff to" if grant else "Revoked staff from"
        if updated:
            self.stdout.write(self.style.SUCCESS(f"{verb}: {', '.join(updated)}"))
        elif not missing:
            self.stdout.write("No changes needed.")
