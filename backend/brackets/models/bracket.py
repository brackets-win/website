from django.db import models

from .bracket_stage import KnockoutStage, GroupStage
from .contestant import IDENTIFIER_VALIDATOR
from .group import GroupMembership


class Bracket(models.Model):
    identifier = models.CharField(
        max_length=64,
        unique=True,
        validators=[IDENTIFIER_VALIDATOR],
        help_text="Stable key for admins (no spaces).",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="brackets/images/", blank=True, null=True
    )
    created_by = models.ForeignKey('bracket.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    # If True, each challenge will randomize seeds; if False, all challenges use the same seeds
    randomize_seeds_per_challenge = models.BooleanField(default=False)
    # Single-elim brackets: optional third-place match (losers of the semifinals).
    has_third_place_match = models.BooleanField(default=False)
    points_champion = models.PositiveIntegerField(default=0)
    points_third_place_winner = models.PositiveIntegerField(default=0)
    show_seeds = models.BooleanField(
        default=True,
        help_text="When false, knockout UI hides seed numbers (e.g. World Cup).",
    )
    # Store bracket-specific metadata (e.g., World Cup third-place combinations)
    metadata = models.JSONField(null=True, blank=True)
    is_reusable = models.BooleanField(
        default=True,
        help_text=(
            "Reusable brackets appear in the admin catalog and can back bracket "
            "challenges. Tournament and poll brackets are one-off (not reusable)."
        ),
    )

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
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_master = models.BooleanField(default=False)
    display_name = models.CharField(max_length=80, blank=True, default="")
    # User picks for group stage / WC third-place pool (JSON).
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['bracket'],
                condition=models.Q(is_master=True),
                name='one_master_per_bracket'
            ),
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

    def get_final_matchup_winner(self):
        """Winner of the knockout final (champion), or None."""
        from .bracket_stage import KnockoutStage

        final_stage = KnockoutStage.objects.filter(
            bracket=self.bracket, is_final=True
        ).first()
        if not final_stage:
            return None
        final_matchup = self.matchup_set.filter(stage=final_stage).first()
        return final_matchup.winner if final_matchup else None

    def get_winner(self):
        """
        Get the winner of this bracket.

        Returns BracketContestant or None
        """
        from .bracket_stage import GroupStage

        final_winner = self.get_final_matchup_winner()
        if final_winner is not None:
            return final_winner

        group_stage = (
            self.bracket.stages.filter(stage_type='GROUP').order_by('order').first()
        )
        if not group_stage:
            return None

        final_group = group_stage.group_set.first()
        if final_group:
            winner_membership = GroupMembership.objects.filter(
                group=final_group,
                final_position=1,
            ).first()
            return winner_membership.contestant if winner_membership else None

        return None

    def calculate_stage_score(self, stage):
        """
        Points for this stage vs the master bracket, or None when not scored yet.
        """
        if self.is_master:
            return None

        master = self.get_master_bracket()
        if not master:
            return None

        if stage.stage_type == 'GROUP':
            return self._calculate_group_stage_score(master, stage)

        if stage.stage_type == 'KNOCKOUT':
            knockout_stage = KnockoutStage.objects.get(pk=stage.pk)
            if knockout_stage.is_third_place:
                return self._calculate_third_place_stage_score(master, stage)
            from brackets.utils.sync_group_knockout import (
                contestants_in_stage_for_scoring,
            )

            user_contestants = contestants_in_stage_for_scoring(self, stage)
            master_contestants = contestants_in_stage_for_scoring(master, stage)
            correct_predictions = user_contestants & master_contestants
            return (
                len(correct_predictions) * knockout_stage.points_per_correct_pick
            )

        return None

    def _calculate_third_place_stage_score(self, master, stage) -> int:
        pts = self.bracket.points_third_place_winner
        if pts <= 0:
            return 0
        user_match = self.matchup_set.filter(stage=stage).first()
        master_match = master.matchup_set.filter(stage=stage).first()
        if not user_match or not master_match:
            return 0
        uw = user_match.winner_id
        mw = master_match.winner_id
        if uw and mw and uw == mw:
            return pts
        return 0

    @staticmethod
    def _position_contestant_id(row: dict, pos) -> int | None:
        cid = row.get(pos)
        if cid is None:
            cid = row.get(str(pos))
        if cid is None:
            return None
        try:
            return int(cid)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _advancing_ids_from_positions(
        cls, group_positions: dict, group_code: str, qualifying: int
    ) -> set[int]:
        row = group_positions.get(group_code)
        if not isinstance(row, dict):
            return set()
        ids: set[int] = set()
        for pos in range(1, qualifying + 1):
            cid = cls._position_contestant_id(row, pos)
            if cid is not None:
                ids.add(cid)
        return ids

    def _calculate_group_stage_score(self, master, stage) -> int:
        gs = GroupStage.objects.get(pk=stage.pk)
        user_gp = (self.metadata or {}).get("group_positions") or {}
        master_gp = (master.metadata or {}).get("group_positions") or {}
        total = 0

        if gs.points_per_exact_position > 0 and isinstance(user_gp, dict) and isinstance(
            master_gp, dict
        ):
            for code, user_row in user_gp.items():
                if not isinstance(user_row, dict):
                    continue
                master_row = master_gp.get(code)
                if not isinstance(master_row, dict):
                    continue
                for pos, user_cid in user_row.items():
                    if user_cid is None:
                        continue
                    try:
                        user_id = int(user_cid)
                    except (TypeError, ValueError):
                        continue
                    master_cid = self._position_contestant_id(master_row, pos)
                    if master_cid is None:
                        continue
                    if user_id == master_cid:
                        total += gs.points_per_exact_position

        if gs.points_per_advancer > 0 and isinstance(user_gp, dict) and isinstance(
            master_gp, dict
        ):
            q = gs.contestants_qualifying_per_group
            for code in master_gp:
                if not isinstance(master_gp.get(code), dict):
                    continue
                user_ids = self._advancing_ids_from_positions(user_gp, code, q)
                master_ids = self._advancing_ids_from_positions(master_gp, code, q)
                total += gs.points_per_advancer * len(user_ids & master_ids)

            user_tp = (self.metadata or {}).get("third_place_advancers") or []
            master_tp = (master.metadata or {}).get("third_place_advancers") or []
            if isinstance(user_tp, list) and isinstance(master_tp, list):
                try:
                    master_tp_ids = {int(x) for x in master_tp if x is not None}
                except (TypeError, ValueError):
                    master_tp_ids = set()
                for cid in user_tp:
                    if cid is None:
                        continue
                    try:
                        if int(cid) in master_tp_ids:
                            total += gs.points_per_advancer
                    except (TypeError, ValueError):
                        continue

        return total

    def calculate_champion_score(self):
        """Points for picking the champion vs master."""
        if self.is_master:
            return None

        master = self.get_master_bracket()
        if not master:
            return None

        pts = self.bracket.points_champion
        if pts <= 0:
            return 0

        user_winner = self.get_final_matchup_winner()
        master_winner = master.get_final_matchup_winner()
        if not user_winner or not master_winner:
            return 0
        if user_winner.id == master_winner.id:
            return pts
        return 0

    def calculate_score(self):
        """
        Calculate this bracket's total score against the master bracket.
        """
        if self.is_master:
            return None

        master = self.get_master_bracket()
        if not master:
            return 0

        score = 0
        for stage in self.bracket.stages.all():
            stage_score = self.calculate_stage_score(stage)
            if stage_score is not None:
                score += stage_score
        champion_score = self.calculate_champion_score()
        if champion_score is not None:
            score += champion_score
        return score

    def calculate_potential_score(self):
        """Maximum achievable points vs the master bracket (partial master allowed)."""
        from brackets.utils.potential_score import calculate_potential_score

        return calculate_potential_score(self)
