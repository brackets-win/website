"""Potential rank on materialized leaderboard scores."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0029_merge_0027_user_username_ci_unique_0028_streak_knockout"),
    ]

    operations = [
        migrations.AddField(
            model_name="userbracket",
            name="leaderboard_potential_rank",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
