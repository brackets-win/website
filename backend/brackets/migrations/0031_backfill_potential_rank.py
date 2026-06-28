"""Backfill potential rank for brackets confirmed before the feature shipped."""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def backfill_potential_ranks(apps, schema_editor):
    # Use the real Bracket model + scoring utils: rank computation depends on
    # model methods (winners, stage scores) that historical models lack.
    from brackets.models import Bracket
    from brackets.utils.potential_rank import persist_potential_ranks_for_bracket

    bracket_ids = list(
        Bracket.objects.filter(
            userbracket__is_master=False,
            userbracket__submitted_at__isnull=False,
        )
        .distinct()
        .values_list("id", flat=True)
    )
    for bracket_id in bracket_ids:
        bracket = Bracket.objects.filter(pk=bracket_id).first()
        if bracket is None:
            continue
        try:
            persist_potential_ranks_for_bracket(bracket)
        except Exception:
            # A single bracket failing must not abort the deploy migration.
            logger.exception(
                "Potential rank backfill failed for bracket %s", bracket_id
            )


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0030_userbracket_leaderboard_potential_rank"),
    ]

    operations = [
        migrations.RunPython(
            backfill_potential_ranks, migrations.RunPython.noop
        ),
    ]
