"""Export catalog data from the current DB for production import."""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

# Reusable site catalog — excludes challenges, picks, and user activity.
CATALOG_MODELS = [
    "bracket.UserTier",
    "bracket.ContestantTag",
    "bracket.Contestant",
    "bracket.BracketTemplate",
    "bracket.Bracket",
    "bracket.GroupStage",
    "bracket.KnockoutStage",
    "bracket.BracketStage",
    "bracket.BracketContestant",
    "bracket.StreakCompetition",
    "bracket.StreakQuestion",
    "bracket.StreakQuestionChoice",
]


class Command(BaseCommand):
    help = (
        "Dump catalog models (contestants, bracket templates, streak competitions) "
        "to JSON for import_dev_seed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="seed/dev_catalog.json",
            help="Output path relative to the backend directory (default: seed/dev_catalog.json)",
        )
        parser.add_argument(
            "--copy-media",
            action="store_true",
            help="Also copy uploaded media files into seed/media/",
        )

    def handle(self, *args, **options):
        backend_dir = Path(settings.BASE_DIR)
        out_path = backend_dir / options["output"]
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", encoding="utf-8") as fh:
            call_command(
                "dumpdata",
                *CATALOG_MODELS,
                "--natural-foreign",
                "--indent",
                "2",
                stdout=fh,
            )

        self.stdout.write(self.style.SUCCESS(f"Wrote {out_path}"))

        if options["copy_media"]:
            media_root = Path(settings.MEDIA_ROOT)
            seed_media = backend_dir / "seed" / "media"
            if seed_media.exists():
                shutil.rmtree(seed_media)
            seed_media.mkdir(parents=True, exist_ok=True)
            for sub in ("contestants", "streak-competitions"):
                src = media_root / sub
                if src.is_dir():
                    shutil.copytree(src, seed_media / sub)
            self.stdout.write(self.style.SUCCESS(f"Copied media to {seed_media}"))
