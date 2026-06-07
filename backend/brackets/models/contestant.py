from django.core.validators import RegexValidator
from django.db import models

IDENTIFIER_VALIDATOR = RegexValidator(
    regex=r"^[a-zA-Z0-9_-]+$",
    message="Use only letters, numbers, underscores, and hyphens (no spaces).",
)


class ContestantTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Contestant(models.Model):
    """Reusable contestant definition (e.g., 'Brazil', 'Stawberry')"""

    identifier = models.CharField(
        max_length=64,
        unique=True,
        validators=[IDENTIFIER_VALIDATOR],
        help_text="Stable key for admins (no spaces).",
    )
    name = models.CharField(max_length=100)
    tags = models.ManyToManyField(
        ContestantTag, blank=True, related_name='contestants')
    image_url = models.URLField(blank=True)
    # Uploaded image (optional). External hotlinks can use image_url.
    photo = models.ImageField(
        upload_to="contestants/photos/", blank=True, null=True
    )
    description = models.TextField(blank=True)
    metadata = models.JSONField(null=True, blank=True)
    created_by = models.ForeignKey('bracket.User', on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class BracketContestant(models.Model):
    """Instance of a contestant within a specific bracket"""
    bracket = models.ForeignKey(
        'bracket.Bracket', on_delete=models.CASCADE, related_name='bracket_contestants')
    contestant = models.ForeignKey(
        Contestant, on_delete=models.SET_NULL, null=True, blank=True)
    # Seed can be: unique values (balanced), duplicate values/tiers (random_balanced), or null (random/custom)
    seed = models.PositiveIntegerField(null=True, blank=True)
    # For overriding name if needed
    name_override = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name_override or (self.contestant.name if self.contestant else f"Contestant {self.id}")

    def get_seed(self):
        """Get the seed for this contestant in this bracket."""
        return self.seed
