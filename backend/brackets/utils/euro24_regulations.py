"""UEFA Euro 2024 third-place combination table (group → R16 third-place slots).

Source: UEFA regulations combination table (also documented on Wikipedia /
BBC Sport). R16 tree slot pairings live in ``brackets/data/euro24/r16_tree_slots.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "euro24"

THIRD_PLACE_COMBINATIONS_PATH = _DATA_DIR / "third_place_combinations.txt"

# Order matches the regulation table: third-place column order for group winners
# who face a third-place qualifier (1B, 1C, 1E, 1F).
FIRST_PLACE_SLOTS_FOR_THIRD_LOOKUP = (
    "1B",
    "1C",
    "1E",
    "1F",
)

# Combination label → option number (for readable option field in metadata).
_COMBO_LABELS = (
    "ABCD",
    "ABCE",
    "ABCF",
    "ABDE",
    "ABDF",
    "ABEF",
    "ACDE",
    "ACDF",
    "ACEF",
    "ADEF",
    "BCDE",
    "BCDF",
    "BCEF",
    "BDEF",
    "CDEF",
)


def teams_to_bit_vector(third_place_teams: list[str]) -> int:
    """
    Map which groups contribute a third-place advancer to a 6-bit value (A..F).

    Each group A–F is one bit (A=0, …, F=5). Tokens must be like ``3A``, ``3F``.
    """
    group_to_bit = {
        "3A": 0,
        "3B": 1,
        "3C": 2,
        "3D": 3,
        "3E": 4,
        "3F": 5,
    }
    bit_vector = 0
    for team in third_place_teams:
        if team in group_to_bit:
            bit_vector |= 1 << group_to_bit[team]
    return bit_vector


def load_third_place_combinations_raw() -> str:
    return THIRD_PLACE_COMBINATIONS_PATH.read_text(encoding="utf-8")


def build_third_place_combinations_lookup(raw_text: str) -> dict[str, dict[str, Any]]:
    """
    Parse combination lines into a bit-vector-keyed lookup used when bracket
    metadata is seeded (same shape as World Cup ``third_place_combinations``).
    """
    first_place_teams = list(FIRST_PLACE_SLOTS_FOR_THIRD_LOOKUP)
    combinations: dict[str, dict[str, Any]] = {}

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            continue
        if not parts[0].isdigit():
            continue

        option_number = parts[0]
        third_place_teams = parts[1:]
        bit_vector = teams_to_bit_vector(third_place_teams)
        matchups = {
            first_place_teams[i]: third_place_teams[i] for i in range(4)
        }
        option_label = option_number
        try:
            idx = int(option_number) - 1
            if 0 <= idx < len(_COMBO_LABELS):
                option_label = _COMBO_LABELS[idx]
        except ValueError:
            pass
        combinations[str(bit_vector)] = {
            "option": option_label,
            "teams": third_place_teams,
            "matchups": matchups,
        }

    return combinations
