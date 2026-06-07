from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0011_activity_types_and_streak"),
    ]

    operations = [
        migrations.AddField(
            model_name="userbracket",
            name="display_name",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
    ]
