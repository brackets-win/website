from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0032_userbracket_leaderboard_next_match_pick"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakchallenge",
            name="knockout_transition_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="streakchallenge",
            name="knockout_round_starts",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="streakquestion",
            name="knockout_only",
            field=models.BooleanField(default=False),
        ),
    ]
