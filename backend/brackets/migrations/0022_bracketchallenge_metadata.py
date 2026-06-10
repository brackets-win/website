from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0021_streak_participant_display_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="bracketchallenge",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
