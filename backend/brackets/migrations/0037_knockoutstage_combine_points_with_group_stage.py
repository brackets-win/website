# Generated manually for KnockoutStage.combine_points_with_group_stage

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0036_groupstage_group_position_picking"),
    ]

    operations = [
        migrations.AddField(
            model_name="knockoutstage",
            name="combine_points_with_group_stage",
            field=models.BooleanField(default=True),
        ),
    ]
