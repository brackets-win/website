from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0020_alter_bracket_is_reusable_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakparticipant",
            name="display_name",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
    ]
