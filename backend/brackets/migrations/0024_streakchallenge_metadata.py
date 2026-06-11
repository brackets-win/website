from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0022_bracketchallenge_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakchallenge",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
