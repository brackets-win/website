from django.db import models


class StreakCompetition(models.Model):
    """Admin-managed question set; grading is shared across linked challenges."""

    name = models.CharField(max_length=100)
    image = models.ImageField(
        upload_to="streak-competitions/images/", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When set, the competition is over; picks are locked and awards are shown.",
    )

    def __str__(self):
        return self.name

    @property
    def is_over(self) -> bool:
        return self.ended_at is not None


class StreakChallenge(models.Model):
    """Joinable pool referencing one competition (many challenges per competition)."""

    class Mode(models.TextChoices):
        STREAK = "STREAK", "Streak"
        KNOCKOUT = "KNOCKOUT", "H2H Knockout"

    name = models.CharField(max_length=100)
    streak_competition = models.ForeignKey(
        StreakCompetition,
        on_delete=models.CASCADE,
        related_name="challenges",
    )
    created_by = models.ForeignKey(
        "bracket.User",
        on_delete=models.CASCADE,
        related_name="streak_challenges_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False)
    join_code = models.CharField(max_length=8, unique=True, null=True, blank=True)
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.STREAK,
    )
    knockout_transition_at = models.DateTimeField(null=True, blank=True)
    # ISO datetimes keyed by round index ("2", "3", …) when each round's picks begin.
    knockout_round_starts = models.JSONField(default=dict, blank=True)
    # Per-round headstart from frozen best streak ("1", "2", …); default on when missing.
    knockout_round_headstart = models.JSONField(default=dict, blank=True)
    knockout_third_place_match = models.BooleanField(default=False)
    # Cached stats revision + payload (see streak_challenge_stats.py).
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name

    @property
    def is_knockout(self) -> bool:
        return self.mode == self.Mode.KNOCKOUT


class StreakParticipant(models.Model):
    streak_challenge = models.ForeignKey(
        StreakChallenge, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey("bracket.User", on_delete=models.CASCADE)
    display_name = models.CharField(max_length=80, blank=True, default="")
    joined_at = models.DateTimeField(auto_now_add=True)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    streak_signed = models.IntegerField(
        default=0,
        help_text="Positive = consecutive wins, negative = consecutive losses.",
    )
    best_win_streak = models.PositiveIntegerField(default=0)
    best_loss_streak = models.PositiveIntegerField(default=0)
    # Frozen at knockout start (regular-season snapshot for awards/headstart).
    frozen_best_win_streak = models.PositiveIntegerField(default=0)
    frozen_wins = models.PositiveIntegerField(default=0)
    frozen_losses = models.PositiveIntegerField(default=0)
    frozen_streak_signed = models.IntegerField(default=0)
    frozen_best_loss_streak = models.PositiveIntegerField(default=0)
    knockout_seed = models.PositiveIntegerField(null=True, blank=True)
    in_knockout_bracket = models.BooleanField(default=False)
    bracket_eliminated_at = models.DateTimeField(null=True, blank=True)
    consolation_wins = models.PositiveIntegerField(default=0)
    consolation_losses = models.PositiveIntegerField(default=0)
    consolation_eligible_from = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["streak_challenge", "user"]

    def __str__(self):
        return f"{self.user.username} in {self.streak_challenge.name}"


class StreakQuestion(models.Model):
    streak_competition = models.ForeignKey(
        StreakCompetition, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.CharField(max_length=500)
    closes_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    correct_choice = models.ForeignKey(
        "StreakQuestionChoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    order = models.PositiveIntegerField(default=0)
    knockout_only = models.BooleanField(default=False)

    class Meta:
        ordering = ["closes_at", "order", "id"]

    def __str__(self):
        return self.text[:60]


class StreakQuestionChoice(models.Model):
    question = models.ForeignKey(
        StreakQuestion, on_delete=models.CASCADE, related_name="choices"
    )
    label = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.label


class StreakPick(models.Model):
    streak_challenge = models.ForeignKey(
        StreakChallenge, on_delete=models.CASCADE, related_name="picks"
    )
    question = models.ForeignKey(
        StreakQuestion, on_delete=models.CASCADE, related_name="picks"
    )
    user = models.ForeignKey("bracket.User", on_delete=models.CASCADE)
    choice = models.ForeignKey(StreakQuestionChoice, on_delete=models.CASCADE)
    picked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["streak_challenge", "question", "user"]

    def __str__(self):
        return f"{self.user.username} → {self.choice.label}"


class StreakKnockout(models.Model):
    class Status(models.TextChoices):
        SETUP = "SETUP", "Setup"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETE = "COMPLETE", "Complete"

    streak_challenge = models.OneToOneField(
        StreakChallenge,
        on_delete=models.CASCADE,
        related_name="knockout",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SETUP,
    )
    current_round = models.PositiveIntegerField(default=0)
    round_started_at = models.DateTimeField(null=True, blank=True)
    headstart_enabled = models.BooleanField(default=True)
    champion = models.ForeignKey(
        StreakParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Knockout for {self.streak_challenge.name}"


class StreakKnockoutMatch(models.Model):
    knockout = models.ForeignKey(
        StreakKnockout,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    round_index = models.PositiveIntegerField()
    position = models.PositiveIntegerField()
    player_a = models.ForeignKey(
        StreakParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knockout_matches_as_a",
    )
    player_b = models.ForeignKey(
        StreakParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knockout_matches_as_b",
    )
    seed_a = models.PositiveIntegerField(default=0)
    seed_b = models.PositiveIntegerField(default=0)
    score_a = models.PositiveIntegerField(null=True, blank=True)
    score_b = models.PositiveIntegerField(null=True, blank=True)
    winner = models.ForeignKey(
        StreakParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knockout_match_wins",
    )
    finalized = models.BooleanField(default=False)
    is_third_place = models.BooleanField(default=False)
    source_match_a = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    source_match_b = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        unique_together = ["knockout", "round_index", "position"]
        ordering = ["round_index", "position"]

    def __str__(self):
        return f"R{self.round_index} M{self.position}"
