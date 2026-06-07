from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="userbracket",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
