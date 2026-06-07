import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bracket", "0010_scoring_config_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="bracketchallenge",
            name="instance_type",
            field=models.CharField(
                choices=[
                    ("CHALLENGE", "Bracket Challenge"),
                    ("TOURNAMENT", "Tournament"),
                    ("POLL", "Poll"),
                ],
                default="CHALLENGE",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="StreakChallenge",
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
                ("is_public", models.BooleanField(default=False)),
                (
                    "join_code",
                    models.CharField(
                        blank=True, max_length=8, null=True, unique=True
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="streak_challenges_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="StreakQuestion",
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
                ("text", models.CharField(max_length=500)),
                ("closes_at", models.DateTimeField()),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "correct_answer",
                    models.CharField(
                        blank=True,
                        choices=[("YES", "Yes"), ("NO", "No")],
                        max_length=3,
                        null=True,
                    ),
                ),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "streak_challenge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="questions",
                        to="bracket.streakchallenge",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
        migrations.CreateModel(
            name="StreakParticipant",
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
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("wins", models.PositiveIntegerField(default=0)),
                ("losses", models.PositiveIntegerField(default=0)),
                (
                    "streak_signed",
                    models.IntegerField(
                        default=0,
                        help_text="Positive = win streak length, negative = loss streak length.",
                    ),
                ),
                (
                    "streak_challenge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="bracket.streakchallenge",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "unique_together": {("streak_challenge", "user")},
            },
        ),
        migrations.CreateModel(
            name="StreakPick",
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
                (
                    "answer",
                    models.CharField(
                        choices=[("YES", "Yes"), ("NO", "No")], max_length=3
                    ),
                ),
                ("picked_at", models.DateTimeField(auto_now_add=True)),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="picks",
                        to="bracket.streakquestion",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "unique_together": {("question", "user")},
            },
        ),
    ]
