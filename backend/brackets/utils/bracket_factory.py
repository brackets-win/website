"""
Create ``Bracket`` rows with stages from a structure key (no ``BracketTemplate`` required).

``BracketTemplate.create_bracket`` delegates here so template rows stay optional shortcuts.
"""

from __future__ import annotations

from typing import Any

from brackets.models import Bracket, GroupStage, KnockoutStage
from brackets.utils.bracket_structure_config import (
    resolved_bracket_scoring,
    resolved_group_stage_options,
    resolved_knockout_defaults,
    resolved_knockout_round_legs,
    resolved_knockout_round_points,
)
from brackets.utils.results_entry import merge_results_entry_into_metadata
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
    is_reusable: bool = True,
) -> Bracket:
    """
    Build a bracket and all stages for ``template_type`` (same values as
    ``BracketTemplate.template_type``).
    """
    if template_type not in VALID_STRUCTURE_TYPES:
        raise ValueError(
            f"template_type must be one of {sorted(VALID_STRUCTURE_TYPES)}"
        )

    scoring = resolved_bracket_scoring(structure_config)
    meta = dict(metadata or {})
    if structure_config and "results_entry" in structure_config:
        meta = merge_results_entry_into_metadata(
            meta, structure_config.get("results_entry")
        )

    bracket = Bracket.objects.create(
        identifier=bracket_identifier,
        name=bracket_name,
        created_by=created_by,
        has_third_place_match=has_third_place,
        show_seeds=show_seeds,
        metadata=meta or None,
        randomize_seeds_per_challenge=randomize_seeds_per_challenge,
        is_reusable=is_reusable,
        **scoring,
    )

    ko_defaults = resolved_knockout_defaults(structure_config)
    ko_round_points = resolved_knockout_round_points(structure_config)
    ko_round_legs = resolved_knockout_round_legs(structure_config)

    def ko_stage_kwargs(round_size: int) -> dict[str, Any]:
        kwargs = dict(ko_defaults)
        kwargs["points_per_correct_pick"] = ko_round_points.get(
            round_size, ko_defaults["points_per_correct_pick"]
        )
        if round_size in ko_round_legs:
            kwargs["number_of_legs"] = ko_round_legs[round_size]
        return kwargs

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
                **ko_stage_kwargs(current_contestants),
            )

            current_contestants //= 2
            order += 1

    elif template_type == "SINGLE_ELIM":
        from brackets.utils.single_elim_byes import single_elim_field_size

        roster = number_of_contestants
        field_size = single_elim_field_size(roster)
        meta["roster_size"] = roster
        if bracket.metadata != meta:
            bracket.metadata = meta
            bracket.save(update_fields=["metadata"])

        current_contestants = field_size
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
                **ko_stage_kwargs(current_contestants),
            )

            current_contestants //= 2
            order += 1

    if has_third_place:
        sync_third_place_structure(bracket)
        ko_cfg = (structure_config or {}).get("knockout") or {}
        if "third_place_number_of_legs" in ko_cfg:
            from brackets.utils.third_place_structure import get_third_place_stage

            tp = get_third_place_stage(bracket)
            if tp is not None:
                legs = int(ko_cfg["third_place_number_of_legs"])
                if legs < 1 or legs > 2:
                    raise ValueError("third_place_number_of_legs must be 1 or 2")
                if tp.number_of_legs != legs:
                    tp.number_of_legs = legs
                    tp.save(update_fields=["number_of_legs"])

    return bracket
