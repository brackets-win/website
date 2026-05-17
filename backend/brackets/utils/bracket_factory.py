"""
Create ``Bracket`` rows with stages from a structure key (no ``BracketTemplate`` required).

``BracketTemplate.create_bracket`` delegates here so template rows stay optional shortcuts.
"""

from __future__ import annotations

from brackets.models import Bracket, GroupStage, KnockoutStage

VALID_STRUCTURE_TYPES = frozenset({"GROUP_KNOCKOUT", "SINGLE_ELIM"})


def create_bracket_with_structure(
    template_type: str,
    bracket_identifier: str,
    bracket_name: str,
    number_of_contestants: int,
    created_by,
    *,
    has_third_place: bool = False,
) -> Bracket:
    """
    Build a bracket and all stages for ``template_type`` (same values as
    ``BracketTemplate.template_type``).
    """
    if template_type not in VALID_STRUCTURE_TYPES:
        raise ValueError(
            f"template_type must be one of {sorted(VALID_STRUCTURE_TYPES)}"
        )

    bracket = Bracket.objects.create(
        identifier=bracket_identifier,
        name=bracket_name,
        created_by=created_by,
        has_third_place_match=(
            has_third_place if template_type == "SINGLE_ELIM" else False
        ),
    )

    if template_type == "GROUP_KNOCKOUT":
        num_groups = number_of_contestants // 4
        contestants_advancing = num_groups * 2

        GroupStage.objects.create(
            bracket=bracket,
            name="Group Stage",
            order=1,
            stage_type="GROUP",
            number_of_contestants=number_of_contestants,
            contestants_advancing=contestants_advancing,
            number_of_groups=num_groups,
            matches_per_contestant=3,
            contestants_qualifying_per_group=2,
            points_per_win=3,
            points_per_tie=1,
            points_per_loss=0,
            ties_allowed=True,
            points_per_correct_pick=1,
        )

        current_contestants = contestants_advancing
        order = 2

        stage_names = {
            64: "Round of 64",
            32: "Round of 32",
            16: "Round of 16",
            8: "Quarterfinals",
            4: "Semifinals",
            2: "Final",
        }

        while current_contestants >= 2:
            is_final = current_contestants == 2
            stage_name = stage_names.get(
                current_contestants, f"Round of {current_contestants}"
            )

            KnockoutStage.objects.create(
                bracket=bracket,
                name=stage_name,
                order=order,
                stage_type="KNOCKOUT",
                number_of_contestants=current_contestants,
                contestants_advancing=None if is_final else current_contestants // 2,
                number_of_legs=1,
                has_extra_time=True,
                has_penalty_shootout=True,
                is_final=is_final,
                points_per_correct_pick=1,
            )

            current_contestants //= 2
            order += 1

    elif template_type == "SINGLE_ELIM":
        current_contestants = number_of_contestants
        order = 1

        stage_names = {
            64: "Round of 64",
            32: "Round of 32",
            16: "Round of 16",
            8: "Quarterfinals",
            4: "Semifinals",
            2: "Final",
        }

        while current_contestants >= 2:
            is_final = current_contestants == 2
            stage_name = stage_names.get(
                current_contestants, f"Round of {current_contestants}"
            )

            KnockoutStage.objects.create(
                bracket=bracket,
                name=stage_name,
                order=order,
                stage_type="KNOCKOUT",
                number_of_contestants=current_contestants,
                contestants_advancing=None if is_final else current_contestants // 2,
                number_of_legs=1,
                has_extra_time=True,
                has_penalty_shootout=True,
                is_final=is_final,
                points_per_correct_pick=1,
            )

            current_contestants //= 2
            order += 1

        if has_third_place:
            KnockoutStage.objects.create(
                bracket=bracket,
                name="Third place",
                order=order,
                stage_type="KNOCKOUT",
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
