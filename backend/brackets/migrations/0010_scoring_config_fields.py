from django.db import migrations, models


def copy_group_pick_points(apps, schema_editor):
    GroupStage = apps.get_model("bracket", "GroupStage")
    for gs in GroupStage.objects.all():
        gs.points_per_exact_position = gs.points_per_correct_pick
        gs.save(update_fields=["points_per_exact_position"])


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0009_bracket_show_seeds"),
    ]

    operations = [
        migrations.AddField(
            model_name="bracket",
            name="points_champion",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bracket",
            name="points_third_place_winner",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="groupstage",
            name="points_per_exact_position",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="groupstage",
            name="points_per_advancer",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(copy_group_pick_points, migrations.RunPython.noop),
    ]
