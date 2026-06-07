"""FIFA 2026 World Cup third-place combination table (group → R32 third-place slots).

Source extract: ``brackets/data/fwc26/third_place_combinations.txt``.
R32 tree slot pairings live in ``brackets/data/fwc26/r32_tree_slots.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "fwc26"

THIRD_PLACE_COMBINATIONS_PATH = _DATA_DIR / "third_place_combinations.txt"

# Order matches the regulation table: third-place column order for group winners
# 1A, 1B, 1D, 1E, 1G, 1I, 1K, 1L (group winners who face a third-place qualifier).
FIRST_PLACE_SLOTS_FOR_THIRD_LOOKUP = (
    "1A",
    "1B",
    "1D",
    "1E",
    "1G",
    "1I",
    "1K",
    "1L",
)

def teams_to_bit_vector(third_place_teams: list[str]) -> int:
    """
    Map which groups contribute a third-place advancer to a 12-bit value (A..L).

    Each group A–L is one bit (A=0, …, L=11). Tokens must be like ``3A``, ``3L``.
    """
    group_to_bit = {
        "3A": 0,
        "3B": 1,
        "3C": 2,
        "3D": 3,
        "3E": 4,
        "3F": 5,
        "3G": 6,
        "3H": 7,
        "3I": 8,
        "3J": 9,
        "3K": 10,
        "3L": 11,
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
    Parse combination lines into a bit-vector-keyed lookup used when bracket metadata
    is seeded (same shape as the former inline ``seed_world_cup_2026`` table).
    """
    first_place_teams = list(FIRST_PLACE_SLOTS_FOR_THIRD_LOOKUP)
    combinations: dict[str, dict[str, Any]] = {}

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 9:
            continue
        if not parts[0].isdigit():
            continue

        option_number = parts[0]
        third_place_teams = parts[1:]
        bit_vector = teams_to_bit_vector(third_place_teams)
        matchups = {
            first_place_teams[i]: third_place_teams[i] for i in range(8)
        }
        combinations[str(bit_vector)] = {
            "option": option_number,
            "teams": third_place_teams,
            "matchups": matchups,
        }

    return combinations
