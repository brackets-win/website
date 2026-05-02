from django.db import models
from django.db.models import Count


class Matchup(models.Model):
    user_bracket = models.ForeignKey(
        'bracket.UserBracket', on_delete=models.CASCADE)
    stage = models.ForeignKey(
        'bracket.BracketStage', on_delete=models.CASCADE)
    position = models.PositiveIntegerField()
    contestant1 = models.ForeignKey(
        'bracket.BracketContestant', related_name='matchup_contestant1', on_delete=models.CASCADE, null=True, blank=True)
    contestant2 = models.ForeignKey(
        'bracket.BracketContestant', related_name='matchup_contestant2', on_delete=models.CASCADE, null=True, blank=True)
    winner = models.ForeignKey('bracket.BracketContestant', related_name='matchup_winner',
                               on_delete=models.SET_NULL, null=True, blank=True)

    # Source tracking for contestants (enables third place matches, double elimination, etc.)
    source_a_matchup = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feeds_team_a_to'
    )
    source_a_uses_winner = models.BooleanField(
        default=True)  # False = use loser

    source_b_matchup = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feeds_team_b_to'
    )
    source_b_uses_winner = models.BooleanField(
        default=True)  # False = use loser

    class Meta:
        ordering = ['stage__order', 'position']
        unique_together = ['user_bracket', 'stage', 'position']

    def __str__(self):
        return f"{self.stage.name} Match {self.position}: {self.contestant1} vs {self.contestant2}"

    def get_next_matchup(self):
        """
        Get the matchup in the next stage that this matchup's winner feeds into.
        Returns None if there is no next knockout matchup (e.g. final — champions
        are not another matchup row; optional third-place game uses loser feeds only).
        """
        from .bracket_stage import KnockoutStage

        try:
            ks = KnockoutStage.objects.get(pk=self.stage_id)
            if ks.is_final:
                return None
        except KnockoutStage.DoesNotExist:
            pass

        next_stage = self.user_bracket.bracket.stages.filter(
            order=self.stage.order + 1
        ).first()

        if not next_stage:
            return None

        # Calculate next position: winners of positions (1,2) go to position 1, (3,4) to 2, etc.
        next_position = (self.position + 1) // 2

        try:
            return Matchup.objects.get(
                user_bracket=self.user_bracket,
                stage=next_stage,
                position=next_position
            )
        except Matchup.DoesNotExist:
            return None

    def is_team_a(self):
        """Returns True if this matchup's winner should be Team A in next matchup."""
        return self.position % 2 == 1

    def get_loser(self):
        """Get the loser of this matchup (the contestant who didn't win)."""
        if not self.winner or not self.contestant1 or not self.contestant2:
            return None

        return self.contestant2 if self.winner == self.contestant1 else self.contestant1

    def propagate_winner(self):
        """
        When a winner is set, automatically propagate winner and loser to subsequent matchups.
        Handles both standard progression and special cases (third place, double elimination).
        """
        if not self.winner:
            return

        # Find all matchups that source from this one
        matchups_sourcing_a = self.feeds_team_a_to.all()
        matchups_sourcing_b = self.feeds_team_b_to.all()

        loser = self.get_loser()

        # Propagate to matchups where this is source A
        for matchup in matchups_sourcing_a:
            if matchup.source_a_uses_winner:
                matchup.contestant1 = self.winner
            else:
                matchup.contestant1 = loser
            matchup.save()

        # Propagate to matchups where this is source B
        for matchup in matchups_sourcing_b:
            if matchup.source_b_uses_winner:
                matchup.contestant2 = self.winner
            else:
                matchup.contestant2 = loser
            matchup.save()

        # Fallback: If no explicit sources, use position-based progression
        if not matchups_sourcing_a and not matchups_sourcing_b:
            next_matchup = self.get_next_matchup()
            if next_matchup:
                if self.is_team_a():
                    next_matchup.contestant1 = self.winner
                else:
                    next_matchup.contestant2 = self.winner
                next_matchup.save()

    def save(self, *args, **kwargs):
        """Override save to auto-propagate winners."""
        super().save(*args, **kwargs)

        # If winner was just set, propagate to next matchup
        if self.winner:
            self.propagate_winner()

    def close_voting(self):
        """
        For poll brackets: count votes and set winner based on majority.
        Tiebreaker: lower seed wins. If seeds tied/null, contestant1 wins.

        Returns the winning contestant.
        """
        votes = UserPick.objects.filter(matchup=self).values(
            'selected_contestant').annotate(vote_count=Count('id')).order_by('-vote_count')

        if votes.exists():
            top_votes = votes.first()['vote_count']

            # Get all contestants with top vote count
            tied_contestants = [v['selected_contestant']
                                for v in votes if v['vote_count'] == top_votes]

            if len(tied_contestants) == 1:
                # Clear winner
                self.winner_id = tied_contestants[0]
            else:
                # Tie: use seed as tiebreaker
                tied_ids = tied_contestants
                winner_id = self._resolve_tie_by_seed(tied_ids)
                self.winner_id = winner_id
        else:
            # No votes: default to contestant1
            self.winner = self.contestant1

        self.save()
        return self.winner

    def _resolve_tie_by_seed(self, contestant_ids):
        """Resolve tie by choosing contestant with lower (better) seed."""
        from .contestant import BracketContestant

        contestants = BracketContestant.objects.filter(id__in=contestant_ids)

        # Sort by seed (nulls last), then by id for consistency
        best = min(contestants, key=lambda c: (
            c.seed if c.seed is not None else float('inf'), c.id))

        return best.id


class UserPick(models.Model):
    matchup = models.ForeignKey(Matchup, on_delete=models.CASCADE)
    user = models.ForeignKey('bracket.User', on_delete=models.CASCADE)
    selected_contestant = models.ForeignKey(
        'bracket.BracketContestant', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} picked {self.selected_contestant}"
