from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0012_userbracket_display_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="bracketchallenge",
            name="max_entries",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.RemoveConstraint(
            model_name="userbracket",
            name="one_bracket_per_user_per_challenge",
        ),
    ]
