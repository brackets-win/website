from django.db import models

from .bracket_stage import KnockoutStage, GroupStage
from .group import GroupMembership


class Bracket(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey('bracket.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    # If True, each challenge will randomize seeds; if False, all challenges use the same seeds
    randomize_seeds_per_challenge = models.BooleanField(default=False)
    # Store bracket-specific metadata (e.g., World Cup third-place combinations)
    metadata = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Override save to auto-create master UserBracket on creation."""
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Create master bracket after initial save (need pk first)
        if is_new:
            UserBracket.objects.create(
                bracket=self,
                user=self.created_by,
                is_master=True
            )

    def get_master_bracket(self):
        """Get the master bracket for this tournament."""
        return self.userbracket_set.get(is_master=True)


class UserBracket(models.Model):
    bracket = models.ForeignKey(Bracket, on_delete=models.CASCADE)
    user = models.ForeignKey('bracket.User', on_delete=models.CASCADE)
    challenge = models.ForeignKey(
        'bracket.BracketChallenge', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_master = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['bracket'],
                condition=models.Q(is_master=True),
                name='one_master_per_bracket'
            ),
            models.UniqueConstraint(
                fields=['user', 'bracket', 'challenge'],
                condition=models.Q(is_master=False),
                name='one_bracket_per_user_per_challenge'
            )
        ]

    def __str__(self):
        if self.is_master:
            return f"Master bracket for {self.bracket.name}"
        if self.challenge:
            return f"{self.user.username}'s bracket for {self.bracket.name} ({self.challenge.name})"
        return f"{self.user.username}'s bracket for {self.bracket.name}"

    def get_master_bracket(self):
        """Get the master bracket for this user bracket's tournament."""
        if self.is_master:
            return self

        try:
            return UserBracket.objects.get(bracket=self.bracket, is_master=True)
        except UserBracket.DoesNotExist:
            return None

    def get_contestants_in_stage(self, stage, as_ids=True):
        """
        Get all contestants that reached this stage in this bracket.

        Args:
            stage: BracketStage instance
            as_ids: If True, returns set of IDs. If False, returns queryset of BracketContestant objects.

        Returns:
            Set of IDs or QuerySet of BracketContestant objects
        """
        contestant_ids = set()
        for matchup in self.matchup_set.filter(stage=stage):
            if matchup.contestant1:
                contestant_ids.add(matchup.contestant1.id)
            if matchup.contestant2:
                contestant_ids.add(matchup.contestant2.id)

        if as_ids:
            return contestant_ids

        from .contestant import BracketContestant
        return BracketContestant.objects.filter(id__in=contestant_ids)

    def get_contestant_names_in_stage(self, stage):
        """
        Get names of all contestants that reached this stage.

        Returns list of contestant names (e.g., ['Spain', 'Germany', 'England', 'Netherlands'])
        """
        contestants = self.get_contestants_in_stage(stage, as_ids=False)
        return [c.contestant.name if c.contestant else c.name_override for c in contestants]

    def get_winner(self):
        """
        Get the winner of this bracket.

        Returns BracketContestant or None
        """
        from .bracket_stage import KnockoutStage, GroupStage

        # Get final stage (highest order)
        final_stage = self.bracket.stages.order_by('-order').first()
        if not final_stage:
            return None

        if final_stage.stage_type == 'KNOCKOUT':
            # Get winner of final matchup (should be only one matchup in final stage)
            knockout_stage = KnockoutStage.objects.get(pk=final_stage.pk)
            if knockout_stage.is_final:
                final_matchup = self.matchup_set.filter(
                    stage=final_stage).first()
                return final_matchup.winner if final_matchup else None
            return None

        elif final_stage.stage_type == 'GROUP':
            # Get 1st place from final group stage
            # If multiple groups, this is ambiguous - could enhance later
            final_group = final_stage.group_set.first()
            if final_group:
                winner_membership = GroupMembership.objects.filter(
                    group=final_group,
                    final_position=1
                ).first()
                return winner_membership.contestant if winner_membership else None

        return None

    def calculate_score(self):
        """
        Calculate this bracket's score against the master bracket.
        Points awarded for correctly predicting contestants advancing to each stage.
        """
        if self.is_master:
            return None  # Master bracket doesn't get scored

        master = self.get_master_bracket()
        if not master:
            return 0

        score = 0

        # Score knockout stages: points for each contestant correctly predicted to reach this stage
        for stage in self.bracket.stages.filter(stage_type='KNOCKOUT'):
            knockout_stage = KnockoutStage.objects.get(pk=stage.pk)

            # Get contestants that reached this stage
            user_contestants = self.get_contestants_in_stage(stage)
            master_contestants = master.get_contestants_in_stage(stage)

            # Award points for each correct prediction
            correct_predictions = user_contestants & master_contestants
            score += len(correct_predictions) * \
                knockout_stage.points_per_correct_pick

        # Group-stage scoring needs per-user placement picks (GroupMembership is bracket-wide).
        # TODO: score group stages once user-specific predictions exist.

        return score
