from django.db import migrations, models
import django.db.models.deletion


def migrate_yes_no_to_choices(apps, schema_editor):
    StreakQuestion = apps.get_model("bracket", "StreakQuestion")
    StreakQuestionChoice = apps.get_model("bracket", "StreakQuestionChoice")
    StreakPick = apps.get_model("bracket", "StreakPick")

    for question in StreakQuestion.objects.all():
        yes = StreakQuestionChoice.objects.create(
            question=question, label="Yes", order=1
        )
        no = StreakQuestionChoice.objects.create(
            question=question, label="No", order=2
        )
        legacy_correct = getattr(question, "correct_answer", None)
        if legacy_correct == "YES":
            question.correct_choice_id = yes.id
            question.save(update_fields=["correct_choice_id"])
        elif legacy_correct == "NO":
            question.correct_choice_id = no.id
            question.save(update_fields=["correct_choice_id"])

        for pick in StreakPick.objects.filter(question_id=question.id):
            legacy_answer = getattr(pick, "answer", None)
            if legacy_answer == "YES":
                pick.choice_id = yes.id
            elif legacy_answer == "NO":
                pick.choice_id = no.id
            if pick.choice_id:
                pick.save(update_fields=["choice_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0015_bracket_template_defaults"),
    ]

    operations = [
        migrations.CreateModel(
            name="StreakQuestionChoice",
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
                ("label", models.CharField(max_length=200)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="choices",
                        to="bracket.streakquestion",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
        migrations.AddField(
            model_name="streakquestion",
            name="correct_choice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="bracket.streakquestionchoice",
            ),
        ),
        migrations.AddField(
            model_name="streakpick",
            name="choice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="bracket.streakquestionchoice",
            ),
        ),
        migrations.RunPython(migrate_yes_no_to_choices, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="streakquestion",
            name="correct_answer",
        ),
        migrations.RemoveField(
            model_name="streakpick",
            name="answer",
        ),
        migrations.AlterField(
            model_name="streakpick",
            name="choice",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="bracket.streakquestionchoice",
            ),
        ),
    ]
