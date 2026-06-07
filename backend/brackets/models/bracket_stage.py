from django.db import models


class BracketStage(models.Model):
    class StageType(models.TextChoices):
        GROUP = 'GROUP', 'Group Stage'
        KNOCKOUT = 'KNOCKOUT', 'Knockout Stage'

    bracket = models.ForeignKey(
        'bracket.Bracket', on_delete=models.CASCADE, related_name='stages')
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField()
    stage_type = models.CharField(
        max_length=20,
        choices=StageType.choices
    )
    number_of_contestants = models.PositiveIntegerField()
    contestants_advancing = models.PositiveIntegerField(null=True, blank=True)
    is_random_draw = models.BooleanField(default=False)
    # Store stage-specific metadata (e.g., custom group-to-knockout mapping)
    metadata = models.JSONField(null=True, blank=True)

    # Submission deadline for this stage (polls or stage-specific challenges)
    submission_deadline = models.DateTimeField(null=True, blank=True)

    # Scoring: points awarded for each correct pick in this stage
    points_per_correct_pick = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.bracket.name} - {self.name} (Stage {self.order})"


class GroupStage(BracketStage):
    class RemainingStrategy(models.TextChoices):
        HIGHEST_PLACE_WITHIN_GROUP = 'HighestPlaceWithinGroup', 'Highest Place Within Group'
        MOST_POINTS_ACROSS_GROUPS = 'MostPointsAcrossGroups', 'Most Points Across Groups'

    number_of_groups = models.PositiveIntegerField()
    matches_per_contestant = models.PositiveIntegerField()
    contestants_qualifying_per_group = models.PositiveIntegerField()
    remaining_spots_strategy = models.CharField(
        max_length=50,
        choices=RemainingStrategy.choices,
        null=True,
        blank=True
    )
    points_per_win = models.PositiveIntegerField(default=3)
    points_per_tie = models.PositiveIntegerField(default=1)
    points_per_loss = models.PositiveIntegerField(default=0)
    points_per_exact_position = models.PositiveIntegerField(default=0)
    points_per_advancer = models.PositiveIntegerField(default=0)
    ties_allowed = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - Group Stage"


class KnockoutStage(BracketStage):
    number_of_legs = models.PositiveIntegerField(default=1)
    has_extra_time = models.BooleanField(default=False)
    has_penalty_shootout = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)
    # Optional third-place game: one matchup fed by semifinal losers (not winners).
    is_third_place = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} - Knockout Stage"
