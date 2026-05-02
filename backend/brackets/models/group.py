from django.db import models


class Group(models.Model):
    bracket = models.ForeignKey(
        'bracket.Bracket', on_delete=models.CASCADE)
    stage = models.ForeignKey(
        'bracket.BracketStage',
        on_delete=models.CASCADE,
        related_name='group_set',
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']
        unique_together = ['stage', 'order']

    @property
    def code(self):
        """
        Get the alphabetical code for this group based on its order.
        order=1 → "A", order=2 → "B", etc.
        """
        if self.order < 1:
            return ""
        # Convert to letter: 1→A, 2→B, ..., 26→Z
        if self.order <= 26:
            return chr(64 + self.order)  # 65 is 'A', so 64+1=65
        # For more than 26 groups, use AA, AB, etc.
        return self._number_to_excel_column(self.order)

    def _number_to_excel_column(self, n):
        """Convert number to Excel-style column (1→A, 27→AA, etc.)."""
        result = ""
        while n > 0:
            n -= 1
            result = chr(65 + (n % 26)) + result
            n //= 26
        return result

    def __str__(self):
        return f"{self.name} ({self.bracket.name})"


class GroupMembership(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    contestant = models.ForeignKey(
        'bracket.BracketContestant', on_delete=models.CASCADE)
    # 1st, 2nd, 3rd, etc.
    final_position = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ['group', 'contestant']

    def get_position_code(self):
        """
        Get the alphanumeric code for this contestant's position.
        Example: Group A, position 1 → "A1"
                 Group B, position 2 → "B2"
        """
        if self.final_position is None:
            return None
        return f"{self.group.code}{self.final_position}"

    def __str__(self):
        if self.final_position:
            return f"{self.contestant} - {self.get_position_code()} in {self.group.name}"
        return f"{self.contestant} in {self.group.name}"
