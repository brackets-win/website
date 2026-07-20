"""Parse optional structure overrides for admin bracket creation."""

from __future__ import annotations

import json
from typing import Any


def _parse_json_field(raw: Any, field_name: str) -> dict[str, Any] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"{field_name} must be valid JSON") from e
        if not isinstance(parsed, dict):
            raise ValueError(f"{field_name} must be a JSON object")
        return parsed
    raise ValueError(f"{field_name} must be a JSON object")


def parse_bracket_metadata(raw: Any) -> dict[str, Any] | None:
    return _parse_json_field(raw, "metadata")


def parse_structure_config(raw: Any) -> dict[str, Any]:
    """Return normalized group_stage / knockout defaults (may be empty)."""
    data = _parse_json_field(raw, "structure_config") or {}
    out: dict[str, Any] = {}
    if "group_stage" in data:
        gs = data["group_stage"]
        if not isinstance(gs, dict):
            raise ValueError("structure_config.group_stage must be an object")
        out["group_stage"] = gs
    if "knockout" in data:
        ko = data["knockout"]
        if not isinstance(ko, dict):
            raise ValueError("structure_config.knockout must be an object")
        out["knockout"] = ko
    for key in ("points_champion", "points_third_place_winner"):
        if key in data:
            out[key] = data[key]
    return out


def _positive_int(value: Any, field: str, *, minimum: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field} must be an integer") from e
    if n < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return n


def _non_negative_int(value: Any, field: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field} must be an integer") from e
    if n < 0:
        raise ValueError(f"{field} must be 0 or greater")
    return n


def _bool_val(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "on", "yes")


def resolved_group_stage_options(
    number_of_contestants: int,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Defaults match ``bracket_factory``; overrides from ``config['group_stage']``."""
    gs = (config or {}).get("group_stage") or {}
    default_groups = number_of_contestants // 4
    num_groups = (
        _positive_int(gs["number_of_groups"], "number_of_groups")
        if "number_of_groups" in gs
        else default_groups
    )
    if number_of_contestants % num_groups != 0:
        raise ValueError(
            "number_of_contestants must be divisible by number_of_groups"
        )
    per_group = number_of_contestants // num_groups
    if per_group < 2:
        raise ValueError("Each group needs at least 2 contestants")

    qualifying = (
        _positive_int(
            gs["contestants_qualifying_per_group"],
            "contestants_qualifying_per_group",
        )
        if "contestants_qualifying_per_group" in gs
        else 2
    )
    if qualifying >= per_group:
        raise ValueError(
            "contestants_qualifying_per_group must be less than teams per group"
        )

    remaining = gs.get("remaining_spots_strategy")
    if remaining is not None and remaining != "":
        remaining = str(remaining)
    else:
        remaining = None

    direct = num_groups * qualifying
    if "contestants_advancing" in gs:
        advancing = _positive_int(gs["contestants_advancing"], "contestants_advancing")
        if advancing < direct:
            raise ValueError(
                "contestants_advancing must be at least groups × qualifying"
            )
    else:
        advancing = direct

    return {
        "number_of_groups": num_groups,
        "matches_per_contestant": (
            _positive_int(gs["matches_per_contestant"], "matches_per_contestant")
            if "matches_per_contestant" in gs
            else 3
        ),
        "contestants_qualifying_per_group": qualifying,
        "contestants_advancing": advancing,
        "remaining_spots_strategy": remaining,
        "points_per_win": (
            _non_negative_int(gs["points_per_win"], "points_per_win")
            if "points_per_win" in gs
            else 3
        ),
        "points_per_tie": (
            _non_negative_int(gs["points_per_tie"], "points_per_tie")
            if "points_per_tie" in gs
            else 1
        ),
        "points_per_loss": (
            _non_negative_int(gs["points_per_loss"], "points_per_loss")
            if "points_per_loss" in gs
            else 0
        ),
        "ties_allowed": _bool_val(gs.get("ties_allowed"), True),
        "points_per_correct_pick": (
            _positive_int(gs["points_per_correct_pick"], "points_per_correct_pick")
            if "points_per_correct_pick" in gs
            else 1
        ),
        "points_per_exact_position": (
            _non_negative_int(gs["points_per_exact_position"], "points_per_exact_position")
            if "points_per_exact_position" in gs
            else (
                _non_negative_int(
                    gs["points_per_correct_pick"], "points_per_correct_pick"
                )
                if "points_per_correct_pick" in gs
                else 1
            )
        ),
        "points_per_advancer": (
            _non_negative_int(gs["points_per_advancer"], "points_per_advancer")
            if "points_per_advancer" in gs
            else 0
        ),
        "is_random_draw": _bool_val(gs.get("is_random_draw"), False),
        "metadata": parse_bracket_metadata(gs.get("metadata")),
    }


def resolved_bracket_scoring(config: dict[str, Any] | None) -> dict[str, int]:
    cfg = config or {}
    return {
        "points_champion": (
            _non_negative_int(cfg["points_champion"], "points_champion")
            if "points_champion" in cfg
            else 0
        ),
        "points_third_place_winner": (
            _non_negative_int(
                cfg["points_third_place_winner"], "points_third_place_winner"
            )
            if "points_third_place_winner" in cfg
            else 0
        ),
    }


def resolved_knockout_defaults(config: dict[str, Any] | None) -> dict[str, Any]:
    ko = (config or {}).get("knockout") or {}
    return {
        "number_of_legs": (
            _positive_int(ko["number_of_legs"], "number_of_legs")
            if "number_of_legs" in ko
            else 1
        ),
        "has_extra_time": _bool_val(ko.get("has_extra_time"), True),
        "has_penalty_shootout": _bool_val(ko.get("has_penalty_shootout"), True),
        "points_per_correct_pick": (
            _positive_int(ko["points_per_correct_pick"], "points_per_correct_pick")
            if "points_per_correct_pick" in ko
            else 1
        ),
        "is_random_draw": _bool_val(ko.get("is_random_draw"), False),
        "metadata": parse_bracket_metadata(ko.get("metadata")),
    }


def resolved_knockout_round_points(config: dict[str, Any] | None) -> dict[int, int]:
    """Optional per-round point overrides, keyed by the round's contestant count.

    Mirrors what the edit flow allows (each knockout stage its own points). The
    key is ``number_of_contestants`` entering that round (e.g. 32, 16, 8, 4, 2),
    which is unique per bracket. Rounds without an entry fall back to the
    knockout default ``points_per_correct_pick``.
    """
    ko = (config or {}).get("knockout") or {}
    raw = ko.get("round_points")
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("round_points must be an object")
    out: dict[int, int] = {}
    for key, value in raw.items():
        try:
            size = int(key)
        except (TypeError, ValueError) as e:
            raise ValueError("round_points keys must be integers") from e
        out[size] = _non_negative_int(value, f"round_points[{key}]")
    return out
