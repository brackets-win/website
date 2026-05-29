"""Bootstrap site catalog without a dev DB export (templates + World Cup bracket)."""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed bracket templates and the FIFA World Cup 2026 master bracket."

    def handle(self, *args, **options):
        call_command("seed_bracket_templates")
        call_command("seed_world_cup_2026")
        self.stdout.write(self.style.SUCCESS("Catalog seed complete."))
