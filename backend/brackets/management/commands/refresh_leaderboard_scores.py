"""Backfill materialized leaderboard scores."""

from django.core.management.base import BaseCommand

from brackets.models import Bracket, UserBracket
from brackets.utils.leaderboard_scoring import (
    refresh_all_submitted_leaderboard_scores_for_bracket,
    refresh_user_bracket_leaderboard_cache,
)


class Command(BaseCommand):
    help = "Recompute stored leaderboard scores for submitted user brackets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bracket-id",
            type=int,
            help="Only refresh user brackets for this bracket id.",
        )

    def handle(self, *args, **options):
        bracket_id = options.get("bracket_id")
        if bracket_id is not None:
            bracket = Bracket.objects.filter(pk=bracket_id).first()
            if bracket is None:
                self.stderr.write(f"Unknown bracket id {bracket_id}")
                return
            count = refresh_all_submitted_leaderboard_scores_for_bracket(bracket)
            self.stdout.write(f"Refreshed {count} user bracket(s) for bracket {bracket_id}.")
            return

        brackets = Bracket.objects.all().order_by("id")
        total = 0
        for bracket in brackets:
            total += refresh_all_submitted_leaderboard_scores_for_bracket(bracket)
        self.stdout.write(f"Refreshed {total} user bracket(s) across {brackets.count()} bracket(s).")
