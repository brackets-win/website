"""Prefix streak competition questions with nation flag emojis."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from brackets.models import StreakCompetition, StreakQuestion
from brackets.utils.streak_question_flags import plan_question_prefixes


class Command(BaseCommand):
    help = (
        "Add nation flag emojis to the start of streak question text only. "
        "Matchup order is learned from explicit 'Team A vs Team B' wording. "
        "Does not touch picks, choices, resolution, closes_at, or order."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "streak_competition_id",
            type=int,
            help="Streak competition primary key",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned changes without writing to the database",
        )

    def handle(self, *args, **options):
        competition_id = options["streak_competition_id"]
        dry_run = options["dry_run"]

        try:
            competition = StreakCompetition.objects.get(pk=competition_id)
        except StreakCompetition.DoesNotExist as exc:
            raise CommandError(f"Streak competition {competition_id} not found.") from exc

        questions = list(
            StreakQuestion.objects.filter(streak_competition=competition)
            .order_by("order", "id")
            .values_list("id", "text")
        )
        if not questions:
            raise CommandError(f"No questions found for {competition.name!r}.")

        report = plan_question_prefixes(questions)

        if report.conflicts:
            self.stdout.write(self.style.WARNING("Conflicting vs order:"))
            for existing, incoming, snippet in report.conflicts:
                self.stdout.write(
                    f"  {existing[0]} vs {existing[1]} vs {incoming[0]} vs {incoming[1]} "
                    f"in {snippet[:80]!r}"
                )

        if report.skipped_no_order:
            self.stdout.write(self.style.WARNING("No canonical order for:"))
            for question_id, text, teams in report.skipped_no_order[:20]:
                self.stdout.write(f"  #{question_id}: {teams} — {text[:100]}")
            remaining = len(report.skipped_no_order) - 20
            if remaining > 0:
                self.stdout.write(f"  ... and {remaining} more")

        if not report.updated:
            self.stdout.write(
                self.style.WARNING("Nothing to update (already prefixed or no match questions).")
            )
            return

        self.stdout.write(
            f"{'Would update' if dry_run else 'Updating'} "
            f"{len(report.updated)} question(s) in {competition.name!r}:"
        )
        for plan in report.updated[:15]:
            self.stdout.write(
                f"  #{plan.question_id} ({plan.team_a} vs {plan.team_b})\n"
                f"    - {plan.old_text[:120]}\n"
                f"    + {plan.new_text[:120]}"
            )
        if len(report.updated) > 15:
            self.stdout.write(f"  ... and {len(report.updated) - 15} more")

        if dry_run:
            return

        with transaction.atomic():
            for plan in report.updated:
                # Single-field SQL update: picks (by question_id), choices,
                # correct_choice, resolved_at, closes_at, and order are unchanged.
                StreakQuestion.objects.filter(pk=plan.question_id).update(
                    text=plan.new_text
                )

        self.stdout.write(self.style.SUCCESS(f"Updated {len(report.updated)} question(s)."))
