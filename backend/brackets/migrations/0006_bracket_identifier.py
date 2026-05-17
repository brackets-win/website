import re

from django.db import migrations, models

import brackets.models.contestant


def _slugify_identifier(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "bracket").strip().lower())
    base = base.strip("-") or "bracket"
    return base[:64]


def populate_identifiers(apps, schema_editor):
    Bracket = apps.get_model("bracket", "Bracket")
    used: set[str] = set()
    for b in Bracket.objects.order_by("id"):
        base = _slugify_identifier(b.name)
        ident = base
        n = 2
        while ident in used:
            suffix = f"-{n}"
            ident = f"{base[: 64 - len(suffix)]}{suffix}"
            n += 1
        used.add(ident)
        b.identifier = ident
        b.save(update_fields=["identifier"])


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0005_contestant_identifier"),
    ]

    operations = [
        migrations.AddField(
            model_name="bracket",
            name="identifier",
            field=models.CharField(
                max_length=64,
                null=True,
                help_text="Stable key for admins (no spaces).",
            ),
        ),
        migrations.RunPython(populate_identifiers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="bracket",
            name="identifier",
            field=models.CharField(
                max_length=64,
                unique=True,
                validators=[brackets.models.contestant.IDENTIFIER_VALIDATOR],
                help_text="Stable key for admins (no spaces).",
            ),
        ),
    ]
