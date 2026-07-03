from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0033_streak_knockout_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakchallenge",
            name="knockout_round_headstart",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
