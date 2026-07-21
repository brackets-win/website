# Generated manually for KnockoutStage.seeding_mode

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0037_knockoutstage_combine_points_with_group_stage"),
    ]

    operations = [
        migrations.AddField(
            model_name="knockoutstage",
            name="seeding_mode",
            field=models.CharField(
                choices=[
                    ("standard", "Standard"),
                    ("reseed", "Reseed"),
                    ("randomize", "Randomize"),
                ],
                default="standard",
                max_length=20,
            ),
        ),
    ]
