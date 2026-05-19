"""
Create ``Bracket`` rows with stages from a structure key (no ``BracketTemplate`` required).

``BracketTemplate.create_bracket`` delegates here so template rows stay optional shortcuts.
"""

from __future__ import annotations

from typing import Any

from brackets.models import Bracket, GroupStage, KnockoutStage
from brackets.utils.bracket_structure_config import (
    resolved_group_stage_options,
    resolved_knockout_defaults,
)
from brackets.utils.third_place_structure import sync_third_place_structure

VALID_STRUCTURE_TYPES = frozenset({"GROUP_KNOCKOUT", "SINGLE_ELIM"})


def create_bracket_with_structure(
    template_type: str,
    bracket_identifier: str,
    bracket_name: str,
    number_of_contestants: int,
    created_by,
    *,
    has_third_place: bool = False,
    show_seeds: bool = True,
    metadata: dict[str, Any] | None = None,
    randomize_seeds_per_challenge: bool = False,
    structure_config: dict[str, Any] | None = None,
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
        has_third_place_match=has_third_place,
        show_seeds=show_seeds,
        metadata=metadata,
        randomize_seeds_per_challenge=randomize_seeds_per_challenge,
    )

    ko_defaults = resolved_knockout_defaults(structure_config)

    if template_type == "GROUP_KNOCKOUT":
        gs_opts = resolved_group_stage_options(
            number_of_contestants, structure_config
        )
        contestants_advancing = gs_opts.pop("contestants_advancing")
        gs_metadata = gs_opts.pop("metadata", None)
        gs_random = gs_opts.pop("is_random_draw")

        GroupStage.objects.create(
            bracket=bracket,
            name="Group Stage",
            order=1,
            stage_type="GROUP",
            number_of_contestants=number_of_contestants,
            contestants_advancing=contestants_advancing,
            is_random_draw=gs_random,
            metadata=gs_metadata,
            **gs_opts,
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
                is_final=is_final,
                **ko_defaults,
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
                is_final=is_final,
                **ko_defaults,
            )

            current_contestants //= 2
            order += 1

    if has_third_place:
        sync_third_place_structure(bracket)

    return bracket
