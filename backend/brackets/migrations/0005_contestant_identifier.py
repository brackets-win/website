import re

from django.db import migrations, models

import brackets.models.contestant


def _slugify_identifier(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "contestant").strip().lower())
    base = base.strip("-") or "contestant"
    return base[:64]


def populate_identifiers(apps, schema_editor):
    Contestant = apps.get_model("bracket", "Contestant")
    used: set[str] = set()
    for c in Contestant.objects.order_by("id"):
        base = _slugify_identifier(c.name)
        ident = base
        n = 2
        while ident in used:
            suffix = f"-{n}"
            ident = f"{base[: 64 - len(suffix)]}{suffix}"
            n += 1
        used.add(ident)
        c.identifier = ident
        c.save(update_fields=["identifier"])


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0004_contestant_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="contestant",
            name="identifier",
            field=models.CharField(
                max_length=64,
                null=True,
                help_text="Stable key for admins (no spaces).",
            ),
        ),
        migrations.RunPython(populate_identifiers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="contestant",
            name="identifier",
            field=models.CharField(
                max_length=64,
                unique=True,
                validators=[brackets.models.contestant.IDENTIFIER_VALIDATOR],
                help_text="Stable key for admins (no spaces).",
            ),
        ),
    ]
