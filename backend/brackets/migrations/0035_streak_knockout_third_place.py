from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0034_streak_knockout_round_headstart"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakchallenge",
            name="knockout_third_place_match",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="streakknockoutmatch",
            name="is_third_place",
            field=models.BooleanField(default=False),
        ),
    ]
