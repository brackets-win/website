from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0006_bracket_identifier"),
    ]

    operations = [
        migrations.AddField(
            model_name="userbracket",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
