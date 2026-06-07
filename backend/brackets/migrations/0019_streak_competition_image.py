from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0018_bracket_is_reusable"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakcompetition",
            name="image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="streak-competitions/images/",
            ),
        ),
    ]
