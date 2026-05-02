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
    created_by = models.ForeignKey('bracket.User', on_delete=models.CASCADE)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def create_bracket(
        self,
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
        from .bracket import Bracket
        from .bracket_stage import GroupStage, KnockoutStage

        bracket = Bracket.objects.create(
            name=bracket_name,
            created_by=created_by,
            has_third_place_match=(
                has_third_place if self.template_type == 'SINGLE_ELIM' else False
            ),
        )

        if self.template_type == 'GROUP_KNOCKOUT':
            # Group stage: groups of 4, 2 qualify per group
            num_groups = number_of_contestants // 4
            contestants_advancing = num_groups * 2

            GroupStage.objects.create(
                bracket=bracket,
                name='Group Stage',
                order=1,
                stage_type='GROUP',
                number_of_contestants=number_of_contestants,
                contestants_advancing=contestants_advancing,
                number_of_groups=num_groups,
                matches_per_contestant=3,
                contestants_qualifying_per_group=2,
                points_per_win=3,
                points_per_tie=1,
                points_per_loss=0,
                ties_allowed=True,
                points_per_correct_pick=1
            )

            # Loop through knockout stages after group
            current_contestants = contestants_advancing
            order = 2

            stage_names = {
                64: 'Round of 64',
                32: 'Round of 32',
                16: 'Round of 16',
                8: 'Quarterfinals',
                4: 'Semifinals',
                2: 'Final'
            }

            while current_contestants >= 2:
                is_final = current_contestants == 2
                stage_name = stage_names.get(
                    current_contestants, f'Round of {current_contestants}')

                KnockoutStage.objects.create(
                    bracket=bracket,
                    name=stage_name,
                    order=order,
                    stage_type='KNOCKOUT',
                    number_of_contestants=current_contestants,
                    contestants_advancing=None if is_final else current_contestants // 2,
                    number_of_legs=1,
                    has_extra_time=True,
                    has_penalty_shootout=True,
                    is_final=is_final,
                    points_per_correct_pick=1
                )

                current_contestants //= 2
                order += 1

        elif self.template_type == 'SINGLE_ELIM':
            # Loop through creating knockout stages until final
            current_contestants = number_of_contestants
            order = 1

            # Stage names based on contestant count
            stage_names = {
                64: 'Round of 64',
                32: 'Round of 32',
                16: 'Round of 16',
                8: 'Quarterfinals',
                4: 'Semifinals',
                2: 'Final'
            }

            while current_contestants >= 2:
                is_final = current_contestants == 2
                stage_name = stage_names.get(
                    current_contestants, f'Round of {current_contestants}')

                KnockoutStage.objects.create(
                    bracket=bracket,
                    name=stage_name,
                    order=order,
                    stage_type='KNOCKOUT',
                    number_of_contestants=current_contestants,
                    contestants_advancing=None if is_final else current_contestants // 2,
                    number_of_legs=1,
                    has_extra_time=True,
                    has_penalty_shootout=True,
                    is_final=is_final,
                    points_per_correct_pick=1
                )

                current_contestants //= 2
                order += 1

            if has_third_place:
                KnockoutStage.objects.create(
                    bracket=bracket,
                    name='Third place',
                    order=order,
                    stage_type='KNOCKOUT',
                    number_of_contestants=2,
                    contestants_advancing=1,
                    number_of_legs=1,
                    has_extra_time=True,
                    has_penalty_shootout=True,
                    is_final=False,
                    is_third_place=True,
                    points_per_correct_pick=1,
                )

        return bracket
