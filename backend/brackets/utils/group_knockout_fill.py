"""How group-stage results fill the first knockout round."""

from __future__ import annotations

from typing import Any

from brackets.data.fwc26.r32_tree_slots import build_r32_group_knockout_mapping
from brackets.utils.bracket_seeding import first_round_seed_pairs
from brackets.utils.group_knockout_mapping import (
    generate_default_group_knockout_mapping,
    set_custom_group_knockout_mapping,
)

STANDARD = "standard"
SEEDING = "seeding"
MAPPING = "mapping"

KNOCKOUT_FILL_METHODS = (STANDARD, SEEDING, MAPPING)


def get_knockout_fill_method(knockout_stage) -> str:
    meta = knockout_stage.metadata or {}
    method = (meta.get("knockout_fill_method") or STANDARD).strip().lower()
    if method not in KNOCKOUT_FILL_METHODS:
        return STANDARD
    return method


def uses_wc_third_place_table(bracket, knockout_stage) -> bool:
    """Mapping fill + FIFA third-place combinations on the bracket."""
    if get_knockout_fill_method(knockout_stage) != MAPPING:
        return False
    meta = bracket.metadata or {}
    return bool(meta.get("third_place_combinations"))


def load_knockout_mapping(
    bracket,
    knockout_stage,
    *,
    num_groups: int | None = None,
) -> list[tuple[int, str, str]]:
    """
    First-round knockout slots: (tree_position, team_a_code, team_b_code).

    - standard: walk groups (A1 vs B2, C1 vs D2, …, B1 vs A2, …)
    - seeding: rank-ordered slots in a normal bracket (1v32, 16v17, …)
    - mapping: explicit ``group_knockout_mapping`` in stage metadata
    """
    method = get_knockout_fill_method(knockout_stage)
    meta = knockout_stage.metadata or {}

    if method == MAPPING:
        mapping_data = meta.get("group_knockout_mapping")
        if mapping_data:
            out: list[tuple[int, str, str]] = []
            for pos_str, teams in mapping_data.items():
                out.append(
                    (int(pos_str), teams["team_a"], teams["team_b"])
                )
            return sorted(out, key=lambda x: x[0])
        if (bracket.metadata or {}).get("tournament_type") == "world_cup_2026":
            return build_r32_group_knockout_mapping()
        return []

    if num_groups is None:
        from brackets.models import GroupStage

        group_stage = (
            bracket.stages.filter(
                stage_type="GROUP", order__lt=knockout_stage.order
            )
            .order_by("-order")
            .first()
        )
        if group_stage is None:
            return []
        gs = GroupStage.objects.get(pk=group_stage.pk)
        num_groups = gs.number_of_groups

    if method == SEEDING:
        return _build_seeding_mapping(num_groups)

    return generate_default_group_knockout_mapping(num_groups)


def _build_seeding_mapping(num_groups: int) -> list[tuple[int, str, str]]:
    """
    Place group finish codes on standard bracket seeds (1v32, 16v17, …).

    Assumes two qualifiers per group (1X and 2X) in group order A, B, C, …
    """
    n = num_groups * 2
    if n < 2 or n & (n - 1):
        raise ValueError(
            "Seeding fill requires total qualifiers to be a power of 2 "
            f"(got {n} from {num_groups} groups)."
        )

    codes: list[str] = []
    group_letters = [chr(65 + i) for i in range(num_groups)]
    for g in group_letters:
        codes.append(f"{g}1")
    for g in group_letters:
        codes.append(f"{g}2")

    pairs = first_round_seed_pairs(n)
    mapping: list[tuple[int, str, str]] = []
    for pos, (seed_a, seed_b) in enumerate(pairs, start=1):
        mapping.append((pos, codes[seed_a - 1], codes[seed_b - 1]))
    return mapping


def apply_knockout_fill_to_stage(
    knockout_stage,
    mapping: list[tuple[int, str, str]],
    *,
    method: str = MAPPING,
) -> None:
    meta = dict(knockout_stage.metadata or {})
    meta["knockout_fill_method"] = method
    knockout_stage.metadata = meta
    knockout_stage.save(update_fields=["metadata"])
    set_custom_group_knockout_mapping(knockout_stage, mapping)
