from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("brackets", "0002_userbracket_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="bracket",
            name="has_third_place_match",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="knockoutstage",
            name="is_third_place",
            field=models.BooleanField(default=False),
        ),
    ]
