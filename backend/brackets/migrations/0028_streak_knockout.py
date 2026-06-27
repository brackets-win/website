from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("brackets", "0027_user_username_ci_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakchallenge",
            name="mode",
            field=models.CharField(
                choices=[("STREAK", "Streak"), ("KNOCKOUT", "H2H Knockout")],
                default="STREAK",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="bracket_eliminated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="consolation_eligible_from",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="consolation_losses",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="consolation_wins",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="frozen_best_loss_streak",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="frozen_best_win_streak",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="frozen_losses",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="frozen_streak_signed",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="frozen_wins",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="in_knockout_bracket",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="streakparticipant",
            name="knockout_seed",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="StreakKnockout",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("SETUP", "Setup"),
                            ("IN_PROGRESS", "In Progress"),
                            ("COMPLETE", "Complete"),
                        ],
                        default="SETUP",
                        max_length=20,
                    ),
                ),
                ("current_round", models.PositiveIntegerField(default=0)),
                ("round_started_at", models.DateTimeField(blank=True, null=True)),
                ("headstart_enabled", models.BooleanField(default=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "champion",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="brackets.streakparticipant",
                    ),
                ),
                (
                    "streak_challenge",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="knockout",
                        to="brackets.streakchallenge",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="StreakKnockoutMatch",
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
                ("round_index", models.PositiveIntegerField()),
                ("position", models.PositiveIntegerField()),
                ("seed_a", models.PositiveIntegerField(default=0)),
                ("seed_b", models.PositiveIntegerField(default=0)),
                ("score_a", models.PositiveIntegerField(blank=True, null=True)),
                ("score_b", models.PositiveIntegerField(blank=True, null=True)),
                ("finalized", models.BooleanField(default=False)),
                (
                    "knockout",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="matches",
                        to="brackets.streakknockout",
                    ),
                ),
                (
                    "player_a",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="knockout_matches_as_a",
                        to="brackets.streakparticipant",
                    ),
                ),
                (
                    "player_b",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="knockout_matches_as_b",
                        to="brackets.streakparticipant",
                    ),
                ),
                (
                    "source_match_a",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="brackets.streakknockoutmatch",
                    ),
                ),
                (
                    "source_match_b",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="brackets.streakknockoutmatch",
                    ),
                ),
                (
                    "winner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="knockout_match_wins",
                        to="brackets.streakparticipant",
                    ),
                ),
            ],
            options={
                "ordering": ["round_index", "position"],
                "unique_together": {("knockout", "round_index", "position")},
            },
        ),
    ]
