"""Import catalog data produced by export_dev_seed."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


DEFAULT_CATALOG_OWNER = "Keaton"


def catalog_owner_natural_key(username: str) -> list[str]:
    if not get_user_model().objects.filter(username=username).exists():
        raise CommandError(
            f"User {username!r} not found. Register that account first, then re-run import."
        )
    return [username]


def fixture_path_for_load(in_path: Path, owner: str) -> tuple[Path, Path | None]:
    """Map exported created_by FKs (system, demo, etc.) to the catalog owner."""
    owner_key = catalog_owner_natural_key(owner)
    raw = json.loads(in_path.read_text(encoding="utf-8"))
    needs_rewrite = any(
        (obj.get("fields") or {}).get("created_by") != owner_key
        for obj in raw
        if (obj.get("fields") or {}).get("created_by") is not None
    )
    if not needs_rewrite:
        return in_path, None

    for obj in raw:
        fields = obj.get("fields")
        if fields and "created_by" in fields:
            fields["created_by"] = owner_key

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".json", prefix="dev_catalog_")
    os.close(tmp_fd)
    tmp = Path(tmp_name)
    tmp.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return tmp, tmp


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
        parser.add_argument(
            "--owner",
            default=DEFAULT_CATALOG_OWNER,
            help=(
                "Username for catalog created_by (must already exist; "
                f"default: {DEFAULT_CATALOG_OWNER})"
            ),
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

        load_path, tmp_path = fixture_path_for_load(in_path, options["owner"])
        try:
            call_command("loaddata", str(load_path))
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        from brackets.models import Bracket

        for bracket in Bracket.objects.all():
            bracket.ensure_master_bracket()

        self.stdout.write(self.style.SUCCESS(f"Loaded {in_path}"))
