from django.db import migrations, models


def mark_activity_brackets_non_reusable(apps, schema_editor):
    Bracket = apps.get_model("bracket", "Bracket")
    BracketChallenge = apps.get_model("bracket", "BracketChallenge")
    ids = set(
        BracketChallenge.objects.filter(
            instance_type__in=("TOURNAMENT", "POLL")
        ).values_list("bracket_id", flat=True)
    )
    if ids:
        Bracket.objects.filter(pk__in=ids).update(is_reusable=False)


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0017_streak_participant_long_streaks"),
    ]

    operations = [
        migrations.AddField(
            model_name="bracket",
            name="is_reusable",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Reusable brackets appear in the admin catalog and can back "
                    "bracket challenges. One-off tournament/poll brackets are not reusable."
                ),
            ),
        ),
        migrations.RunPython(
            mark_activity_brackets_non_reusable,
            migrations.RunPython.noop,
        ),
    ]
