from django.db import models


class BracketChallenge(models.Model):
    """
    A bracket instance where users participate.
    Can be CHALLENGE (competitive predictions) or POLL (social voting).
    """
    INSTANCE_TYPE_CHOICES = [
        ('CHALLENGE', 'Challenge'),
        ('POLL', 'Poll')
    ]

    name = models.CharField(max_length=100)
    bracket = models.ForeignKey('bracket.Bracket', on_delete=models.CASCADE)
    instance_type = models.CharField(
        max_length=20, choices=INSTANCE_TYPE_CHOICES, default='CHALLENGE')
    created_by = models.ForeignKey(
        'bracket.User', on_delete=models.CASCADE, related_name='challenges_created')
    created_at = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False)
    join_code = models.CharField(
        max_length=8, unique=True, null=True, blank=True)
    # Overall submission deadline (prevent submissions after tournament starts)
    submission_deadline = models.DateTimeField(null=True, blank=True)
    # If bracket.randomize_seeds_per_challenge is True, stores {bracket_contestant_id: actual_seed}
    seed_mapping = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.bracket.name}"


class ChallengeParticipant(models.Model):
    """
    Represents a user's participation in a bracket challenge.
    """
    challenge = models.ForeignKey(BracketChallenge, on_delete=models.CASCADE)
    user = models.ForeignKey('bracket.User', on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['challenge', 'user']

    def __str__(self):
        return f"{self.user.username} in {self.challenge.name}"
