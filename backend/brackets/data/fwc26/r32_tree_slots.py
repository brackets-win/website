"""
World Cup 2026 Round of 32: group-finish codes at each bracket tree position.

Derived from knockout_matchups.tsv winner feeders. Tree position 1 is the top
R32 game; (1,2)→R16-1, (3,4)→R16-2, … Left half (pos 1–8) feeds SF M101;
right half (pos 9–16) feeds SF M102.

Examples (same half → M101): M73 (2A/2B), M77 (1I), M83 (2K/2L).
"""

from __future__ import annotations

# (tree position 1..16, team_a code, team_b code)
R32_TREE_SLOTS: tuple[tuple[int, str, str], ...] = (
  # M101 half (M97 / M98 quarters)
    (1, "E1", "3E"),   # M74
    (2, "I1", "3I"),   # M77
    (3, "A2", "B2"),   # M73
    (4, "F1", "C2"),   # M75
    (5, "K2", "L2"),   # M83
    (6, "H1", "J2"),   # M84
    (7, "D1", "3D"),   # M81
    (8, "G1", "3G"),   # M82
  # M102 half (M99 / M100 quarters)
    (9, "C1", "F2"),   # M76
    (10, "E2", "I2"),  # M78
    (11, "A1", "3A"),  # M79
    (12, "L1", "3L"),  # M80
    (13, "J1", "H2"),  # M86
    (14, "D2", "G2"),  # M88
    (15, "B1", "3B"),  # M85
    (16, "K1", "3K"),  # M87
)


def build_r32_group_knockout_mapping() -> list[tuple[int, str, str]]:
    return [(pos, team_a, team_b) for pos, team_a, team_b in R32_TREE_SLOTS]


def build_finisher_to_bracket_seed() -> dict[str, int]:
    """Group-finish code → standard 32-team bracket seed (from tree slot + pairing)."""
    from brackets.utils.bracket_seeding import first_round_seed_pairs

    pairs = first_round_seed_pairs(32)
    seeds: dict[str, int] = {}
    for (pos, team_a, team_b), (seed_a, seed_b) in zip(R32_TREE_SLOTS, pairs, strict=True):
        seeds[team_a] = seed_a
        seeds[team_b] = seed_b
    return seeds


# Derived once at import — not a separate hand-maintained table.
FINISHER_TO_BRACKET_SEED: dict[str, int] = build_finisher_to_bracket_seed()
