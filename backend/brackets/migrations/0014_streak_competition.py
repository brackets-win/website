import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_streak_to_competitions(apps, schema_editor):
    StreakChallenge = apps.get_model("bracket", "StreakChallenge")
    StreakCompetition = apps.get_model("bracket", "StreakCompetition")
    StreakQuestion = apps.get_model("bracket", "StreakQuestion")
    StreakPick = apps.get_model("bracket", "StreakPick")

    for challenge in StreakChallenge.objects.all():
        competition = StreakCompetition.objects.create(name=challenge.name)
        challenge.streak_competition_id = competition.id
        challenge.save(update_fields=["streak_competition_id"])

        for question in StreakQuestion.objects.filter(streak_challenge_id=challenge.id):
            question.streak_competition_id = competition.id
            question.save(update_fields=["streak_competition_id"])

        question_ids = list(
            StreakQuestion.objects.filter(streak_competition_id=competition.id).values_list(
                "id", flat=True
            )
        )
        for pick in StreakPick.objects.filter(question_id__in=question_ids):
            if pick.streak_challenge_id is None:
                pick.streak_challenge_id = challenge.id
                pick.save(update_fields=["streak_challenge_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0013_challenge_max_entries"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StreakCompetition",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(
            model_name="streakchallenge",
            name="streak_competition",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="challenges",
                to="bracket.streakcompetition",
            ),
        ),
        migrations.AddField(
            model_name="streakquestion",
            name="streak_competition",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="bracket.streakcompetition",
            ),
        ),
        migrations.AddField(
            model_name="streakpick",
            name="streak_challenge",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="picks",
                to="bracket.streakchallenge",
            ),
        ),
        migrations.RunPython(
            migrate_streak_to_competitions,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="streakquestion",
            name="streak_challenge",
        ),
        migrations.AlterField(
            model_name="streakchallenge",
            name="streak_competition",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="challenges",
                to="bracket.streakcompetition",
            ),
        ),
        migrations.AlterField(
            model_name="streakquestion",
            name="streak_competition",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="bracket.streakcompetition",
            ),
        ),
        migrations.AlterField(
            model_name="streakpick",
            name="streak_challenge",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="picks",
                to="bracket.streakchallenge",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="streakpick",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="streakpick",
            unique_together={("streak_challenge", "question", "user")},
        ),
    ]
