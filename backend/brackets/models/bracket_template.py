from django.db import models


class BracketTemplate(models.Model):
    """
    Reusable blueprint for common bracket structures.
    Examples: "Group & Knockout", "Single Elimination"
    """
    TEMPLATE_TYPE_CHOICES = [
        ('GROUP_KNOCKOUT', 'Group & Knockout'),
        ('SINGLE_ELIM', 'Single Elimination'),
    ]

    name = models.CharField(max_length=100)
    template_type = models.CharField(
        max_length=20, choices=TEMPLATE_TYPE_CHOICES)
    description = models.TextField(blank=True)
    default_number_of_contestants = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Suggested team count when an admin picks this template.',
    )
    created_by = models.ForeignKey('bracket.User', on_delete=models.CASCADE)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def create_bracket(
        self,
        bracket_identifier,
        bracket_name,
        number_of_contestants,
        created_by,
        *,
        has_third_place=False,
    ):
        """
        Create a new Bracket from this template based on template_type.

        Returns the created Bracket instance with all stages populated.
        """
        from brackets.utils.bracket_factory import create_bracket_with_structure

        return create_bracket_with_structure(
            self.template_type,
            bracket_identifier,
            bracket_name,
            number_of_contestants,
            created_by,
            has_third_place=has_third_place,
        )
