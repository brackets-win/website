import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bracket', '0031_backfill_potential_rank'),
    ]

    operations = [
        migrations.AddField(
            model_name='userbracket',
            name='leaderboard_next_match_pick',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='bracket.bracketcontestant',
            ),
        ),
    ]
