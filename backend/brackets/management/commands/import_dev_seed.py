"""Import catalog data produced by export_dev_seed."""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Load catalog JSON (and optional media) from export_dev_seed."

    def _flush_catalog(self) -> None:
        from brackets.models import (
            Bracket,
            BracketContestant,
            BracketStage,
            BracketTemplate,
            Contestant,
            ContestantTag,
            GroupStage,
            KnockoutStage,
            StreakCompetition,
            StreakQuestion,
            StreakQuestionChoice,
            UserTier,
        )

        StreakQuestionChoice.objects.all().delete()
        StreakQuestion.objects.all().delete()
        StreakCompetition.objects.all().delete()
        BracketContestant.objects.all().delete()
        BracketStage.objects.all().delete()
        KnockoutStage.objects.all().delete()
        GroupStage.objects.all().delete()
        Bracket.objects.all().delete()
        BracketTemplate.objects.all().delete()
        Contestant.objects.all().delete()
        ContestantTag.objects.all().delete()
        UserTier.objects.all().delete()
        self.stdout.write("Cleared existing catalog rows.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            default="seed/dev_catalog.json",
            help="Input path relative to the backend directory (default: seed/dev_catalog.json)",
        )
        parser.add_argument(
            "--copy-media",
            action="store_true",
            help="Copy seed/media/ into MEDIA_ROOT before loading data",
        )
        parser.add_argument(
            "--flush-catalog",
            action="store_true",
            help="Delete existing catalog rows before import (destructive)",
        )

    def handle(self, *args, **options):
        backend_dir = Path(settings.BASE_DIR)
        in_path = backend_dir / options["input"]
        if not in_path.is_file():
            raise CommandError(f"Missing seed file: {in_path}")

        if options["copy_media"]:
            seed_media = backend_dir / "seed" / "media"
            if not seed_media.is_dir():
                raise CommandError(
                    f"Missing {seed_media}. Re-run export_dev_seed --copy-media locally."
                )
            media_root = Path(settings.MEDIA_ROOT)
            media_root.mkdir(parents=True, exist_ok=True)
            for child in seed_media.iterdir():
                dest = media_root / child.name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(child, dest)
            self.stdout.write(self.style.SUCCESS(f"Copied media into {media_root}"))

        if options["flush_catalog"]:
            self._flush_catalog()

        call_command("loaddata", str(in_path))
        self.stdout.write(self.style.SUCCESS(f"Loaded {in_path}"))
