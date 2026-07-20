"""
UEFA Euro 2024 Round of 16: group-finish codes at each bracket tree position.

Tree positions follow standard 16-team seed pairs (1v16, 8v9, 4v13, …).
Later rounds use normal tree progression: R16 positions (1,2)→QF-1, (3,4)→QF-2, …
"""

from __future__ import annotations

# (tree position 1..8, team_a code, team_b code)
# Order matches UEFA R16 geometry mapped onto seed pairs 1v16, 8v9, 4v13, …
R16_TREE_SLOTS: tuple[tuple[int, str, str], ...] = (
    (1, "A1", "C2"),   # 1 vs 16
    (2, "B1", "3B"),   # 8 vs 9  — third-place slot via Excel combination table
    (3, "F1", "3F"),   # 4 vs 13 — A/B/C3
    (4, "D2", "E2"),   # 5 vs 12
    (5, "D1", "F2"),   # 2 vs 15
    (6, "E1", "3E"),   # 7 vs 10 — A/B/C/D3
    (7, "C1", "3C"),   # 3 vs 14 — D/E/F3
    (8, "A2", "B2"),   # 6 vs 11
)


def build_r16_group_knockout_mapping() -> list[tuple[int, str, str]]:
    return [(pos, team_a, team_b) for pos, team_a, team_b in R16_TREE_SLOTS]


def build_finisher_to_bracket_seed() -> dict[str, int]:
    """Group-finish code → standard 16-team bracket seed (from tree slot + pairing)."""
    from brackets.utils.bracket_seeding import first_round_seed_pairs

    pairs = first_round_seed_pairs(16)
    seeds: dict[str, int] = {}
    for (pos, team_a, team_b), (seed_a, seed_b) in zip(R16_TREE_SLOTS, pairs, strict=True):
        seeds[team_a] = seed_a
        seeds[team_b] = seed_b
    return seeds


# Derived once at import — not a separate hand-maintained table.
FINISHER_TO_BRACKET_SEED: dict[str, int] = build_finisher_to_bracket_seed()
