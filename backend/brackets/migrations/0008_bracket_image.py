from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0007_userbracket_submitted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="bracket",
            name="image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="brackets/images/",
            ),
        ),
    ]
