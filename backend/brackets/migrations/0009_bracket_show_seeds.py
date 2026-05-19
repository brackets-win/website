from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0008_bracket_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="bracket",
            name="show_seeds",
            field=models.BooleanField(
                default=True,
                help_text="When false, knockout UI hides seed numbers (e.g. World Cup).",
            ),
        ),
    ]
