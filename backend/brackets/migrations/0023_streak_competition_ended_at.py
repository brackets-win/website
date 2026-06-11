from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0024_streakchallenge_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakcompetition",
            name="ended_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When set, the competition is over; picks are locked and awards are shown.",
                null=True,
            ),
        ),
    ]
