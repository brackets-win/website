from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0003_third_place_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="contestant",
            name="photo",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="contestants/photos/",
            ),
        ),
    ]
