from django.core.management.base import BaseCommand, CommandError

from brackets.management.commands.seed_world_cup_2026 import WC_IDENTIFIER
from brackets.models import Bracket
from brackets.utils.fix_fwc26_r32_positions import fix_fwc26_r32_tree_positions


class Command(BaseCommand):
    help = (
        "Move Round of 32 matchups to correct bracket tree positions for "
        "fifa-world-cup-2026 (fixes brackets seeded before r32_tree_slots)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "bracket",
            nargs="?",
            default=WC_IDENTIFIER,
            help=f"Bracket identifier (default: {WC_IDENTIFIER})",
        )

    def handle(self, *args, **options):
        ident = options["bracket"]
        try:
            bracket = Bracket.objects.get(identifier=ident)
        except Bracket.DoesNotExist as exc:
            raise CommandError(f"No bracket with identifier {ident!r}") from exc

        n = fix_fwc26_r32_tree_positions(bracket)
        if n:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Repositioned R32 for {n} user bracket(s) on {ident}."
                )
            )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    f"No R32 repositioning needed for {ident} "
                    "(already on tree slots or not a WC 2026 bracket)."
                )
            )
