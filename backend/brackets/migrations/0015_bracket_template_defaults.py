from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bracket', '0014_streak_competition'),
    ]

    operations = [
        migrations.AddField(
            model_name='brackettemplate',
            name='default_number_of_contestants',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Suggested team count when an admin picks this template.',
                null=True,
            ),
        ),
    ]
