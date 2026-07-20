"""Bootstrap site catalog without a dev DB export (templates + tournament brackets)."""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Seed bracket templates and master tournament brackets "
        "(FIFA World Cup 2026, UEFA Euro 2024)."
    )

    def handle(self, *args, **options):
        call_command("seed_bracket_templates")
        call_command("seed_world_cup_2026")
        call_command("seed_euro_2024")
        self.stdout.write(self.style.SUCCESS("Catalog seed complete."))
