"""Materialized leaderboard scores on UserBracket."""

from django.db import migrations, models

LEADERBOARD_SCORES_KEY = "leaderboard_scores"


def copy_scores_from_metadata(apps, schema_editor):
    UserBracket = apps.get_model("bracket", "UserBracket")
    to_update = []
    for ub in UserBracket.objects.filter(
        is_master=False, submitted_at__isnull=False
    ).iterator():
        meta = ub.metadata if isinstance(ub.metadata, dict) else {}
        cache = meta.get(LEADERBOARD_SCORES_KEY)
        if not isinstance(cache, dict):
            continue
        stage_scores = cache.get("stage_scores")
        if not isinstance(stage_scores, dict):
            stage_scores = {}
        ub.leaderboard_score = cache.get("score")
        ub.leaderboard_potential = cache.get("potential")
        ub.leaderboard_stage_scores = stage_scores
        ub.leaderboard_scores_revision = cache.get("revision")
        to_update.append(ub)
    if to_update:
        UserBracket.objects.bulk_update(
            to_update,
            [
                "leaderboard_score",
                "leaderboard_potential",
                "leaderboard_stage_scores",
                "leaderboard_scores_revision",
            ],
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0023_streak_competition_ended_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="userbracket",
            name="leaderboard_score",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userbracket",
            name="leaderboard_potential",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userbracket",
            name="leaderboard_stage_scores",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="userbracket",
            name="leaderboard_scores_revision",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.RunPython(copy_scores_from_metadata, migrations.RunPython.noop),
    ]
