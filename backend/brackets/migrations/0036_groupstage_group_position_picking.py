# Generated manually for group_position_picking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0035_streak_knockout_third_place"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupstage",
            name="group_position_picking",
            field=models.CharField(
                choices=[
                    ("all", "All"),
                    ("qualifying_only", "Qualifying Only"),
                ],
                default="all",
                max_length=32,
            ),
        ),
    ]
