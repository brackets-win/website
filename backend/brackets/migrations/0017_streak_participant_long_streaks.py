from django.db import migrations, models


def backfill_long_streaks(apps, schema_editor):
    StreakChallenge = apps.get_model("bracket", "StreakChallenge")
    from brackets.utils.streak_scoring import recalculate_streak_challenge

    for challenge_id in StreakChallenge.objects.values_list("id", flat=True):
        recalculate_streak_challenge(challenge_id)


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0016_streak_question_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakparticipant",
            name="best_win_streak",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="best_loss_streak",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_long_streaks, migrations.RunPython.noop),
    ]
