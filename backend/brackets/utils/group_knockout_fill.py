"""How group-stage results fill the first knockout round."""

from __future__ import annotations

import random
from typing import Any

from brackets.data.euro24.r16_tree_slots import build_r16_group_knockout_mapping
from brackets.data.fwc26.r32_tree_slots import build_r32_group_knockout_mapping
from brackets.utils.bracket_seeding import first_round_seed_pairs
from brackets.utils.group_knockout_mapping import (
    generate_default_group_knockout_mapping,
    set_custom_group_knockout_mapping,
)

STANDARD = "standard"
SEEDING = "seeding"
RANDOMIZE = "randomize"
MAPPING = "mapping"

KNOCKOUT_FILL_METHODS = (STANDARD, SEEDING, RANDOMIZE, MAPPING)

# Tournaments whose first KO round uses explicit mapping (+ optional third-place table).
MAPPING_TOURNAMENT_TYPES = frozenset({"world_cup_2026", "euro_2024"})


def _bracket_meta(bracket) -> dict[str, Any]:
    if bracket is None:
        return {}
    meta = getattr(bracket, "metadata", None)
    return meta if isinstance(meta, dict) else {}


def _mapping_dict_from_meta(meta: dict[str, Any] | None) -> dict | None:
    if not meta:
        return None
    raw = meta.get("group_knockout_mapping")
    return raw if isinstance(raw, dict) and raw else None


def _parse_mapping_dict(
    mapping_data: dict,
) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    for pos_str, teams in mapping_data.items():
        out.append((int(pos_str), teams["team_a"], teams["team_b"]))
    return sorted(out, key=lambda x: x[0])


def get_knockout_fill_method(knockout_stage, bracket=None) -> str:
    """
    Resolve how group finishes map into the first knockout round.

    Prefer mapping when stage/bracket already carries a custom map, third-place
    combination table, or known tournament_type — except an explicit
    ``randomize`` fill keeps that mode (the stored map is the frozen draw).
    """
    meta = knockout_stage.metadata or {}
    if bracket is None:
        try:
            bracket = knockout_stage.bracket
        except AttributeError:
            bracket = None
    bmeta = _bracket_meta(bracket)

    explicit = meta.get("knockout_fill_method")
    explicit_s = (
        str(explicit).strip().lower()
        if explicit is not None and str(explicit).strip()
        else ""
    )
    if explicit_s == RANDOMIZE:
        return RANDOMIZE

    if _mapping_dict_from_meta(meta) or _mapping_dict_from_meta(bmeta):
        return MAPPING
    if bmeta.get("third_place_combinations"):
        return MAPPING
    if bmeta.get("tournament_type") in MAPPING_TOURNAMENT_TYPES:
        return MAPPING

    if explicit_s in KNOCKOUT_FILL_METHODS:
        return explicit_s
    return STANDARD


def ensure_knockout_fill_method_persisted(
    knockout_stage, bracket, *, method: str | None = None
) -> None:
    """Write inferred fill method to stage metadata when missing."""
    resolved = method or get_knockout_fill_method(knockout_stage, bracket)
    meta = dict(knockout_stage.metadata or {})
    if meta.get("knockout_fill_method") == resolved:
        return
    meta["knockout_fill_method"] = resolved
    knockout_stage.metadata = meta
    knockout_stage.save(update_fields=["metadata"])


def uses_wc_third_place_table(bracket, knockout_stage) -> bool:
    """True when the bracket has a third-place combination lookup table."""
    return bool(_bracket_meta(bracket).get("third_place_combinations"))


def _qualifier_codes(num_groups: int) -> list[str]:
    group_letters = [chr(65 + i) for i in range(num_groups)]
    return [f"{g}1" for g in group_letters] + [f"{g}2" for g in group_letters]


def build_randomize_mapping(
    num_groups: int,
    *,
    rng: random.Random | None = None,
) -> list[tuple[int, str, str]]:
    """
    Shuffle group qualifiers into first-round slots.

    Prefers pairings that avoid the same group meeting in R1 when possible.
    """
    codes = _qualifier_codes(num_groups)
    n = len(codes)
    if n < 2 or n & (n - 1):
        raise ValueError(
            "Randomize fill requires total qualifiers to be a power of 2 "
            f"(got {n} from {num_groups} groups)."
        )
    rng = rng or random.Random()

    def to_mapping(order: list[str]) -> list[tuple[int, str, str]]:
        out: list[tuple[int, str, str]] = []
        for pos in range(1, n // 2 + 1):
            out.append((pos, order[2 * (pos - 1)], order[2 * (pos - 1) + 1]))
        return out

    def same_group_clash(order: list[str]) -> bool:
        for i in range(0, n, 2):
            if order[i][0] == order[i + 1][0]:
                return True
        return False

    best = list(codes)
    rng.shuffle(best)
    for _ in range(40):
        cand = list(codes)
        rng.shuffle(cand)
        if not same_group_clash(cand):
            best = cand
            break
        best = cand
    return to_mapping(best)


def ensure_randomized_group_knockout_draw(
    bracket,
    knockout_stage,
    *,
    num_groups: int,
    ready: bool,
) -> bool:
    """
    When fill method is randomize and all groups are ready, freeze one draw.

    Returns True if a new draw was written.
    """
    if get_knockout_fill_method(knockout_stage, bracket) != RANDOMIZE:
        return False
    meta = dict(knockout_stage.metadata or {})
    if _mapping_dict_from_meta(meta):
        return False
    if not ready:
        return False
    mapping = build_randomize_mapping(num_groups)
    set_custom_group_knockout_mapping(knockout_stage, mapping)
    knockout_stage.refresh_from_db()
    meta = dict(knockout_stage.metadata or {})
    meta["knockout_fill_method"] = RANDOMIZE
    knockout_stage.metadata = meta
    knockout_stage.save(update_fields=["metadata"])
    return True


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
    - randomize: shuffled qualifiers (persisted as ``group_knockout_mapping``)
    - mapping: explicit ``group_knockout_mapping`` on stage or bracket metadata
    """
    method = get_knockout_fill_method(knockout_stage, bracket)
    stage_meta = knockout_stage.metadata or {}
    bmeta = _bracket_meta(bracket)

    if method == RANDOMIZE:
        mapping_data = _mapping_dict_from_meta(stage_meta) or _mapping_dict_from_meta(
            bmeta
        )
        if mapping_data:
            return _parse_mapping_dict(mapping_data)
        return []

    if method == MAPPING:
        mapping_data = _mapping_dict_from_meta(stage_meta) or _mapping_dict_from_meta(
            bmeta
        )
        if mapping_data:
            return _parse_mapping_dict(mapping_data)
        tournament_type = bmeta.get("tournament_type")
        if tournament_type == "world_cup_2026":
            return build_r32_group_knockout_mapping()
        if tournament_type == "euro_2024":
            return build_r16_group_knockout_mapping()
        # Euro-shaped combination table (1B/1C/1E/1F) without tournament_type.
        combos = bmeta.get("third_place_combinations")
        if isinstance(combos, dict) and combos:
            sample = next(iter(combos.values()), None)
            matchups = (
                sample.get("matchups") if isinstance(sample, dict) else None
            )
            if isinstance(matchups, dict) and "1F" in matchups:
                return build_r16_group_knockout_mapping()
            if isinstance(matchups, dict) and "1L" in matchups:
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

    codes = _qualifier_codes(num_groups)
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
