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

        result = fix_fwc26_r32_tree_positions(bracket)
        if not isinstance(result, tuple):
            self.stdout.write(
                self.style.NOTICE(
                    f"Skipped {ident} (not a WC 2026 bracket or no R32 stage)."
                )
            )
            return
        repositioned, resynced = result
        self.stdout.write(
            self.style.SUCCESS(
                f"Applied FIFA R32 mapping on {ident}: "
                f"repositioned {repositioned} user bracket(s), "
                f"re-synced group picks on {resynced} user bracket(s)."
            )
        )
