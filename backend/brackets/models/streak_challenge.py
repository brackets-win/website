from django.db import models


class StreakCompetition(models.Model):
    """Admin-managed question set; grading is shared across linked challenges."""

    name = models.CharField(max_length=100)
    image = models.ImageField(
        upload_to="streak-competitions/images/", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class StreakChallenge(models.Model):
    """Joinable pool referencing one competition (many challenges per competition)."""

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

    def __str__(self):
        return self.name


class StreakParticipant(models.Model):
    streak_challenge = models.ForeignKey(
        StreakChallenge, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey("bracket.User", on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    streak_signed = models.IntegerField(
        default=0,
        help_text="Positive = consecutive wins, negative = consecutive losses.",
    )
    best_win_streak = models.PositiveIntegerField(default=0)
    best_loss_streak = models.PositiveIntegerField(default=0)

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

    class Meta:
        ordering = ["order", "id"]

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
