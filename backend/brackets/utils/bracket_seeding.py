"""Standard single-elimination bracket seed order (any power-of-two field size)."""

from __future__ import annotations


def bracket_seed_order(num_contestants: int) -> list[int]:
    """
    Seeds 1..N in first-round *tree* order (top game first, then downward).

    For N=8: [1, 8, 4, 5, 2, 7, 3, 6] → games 1v8, 4v5, 2v7, 3v6.
  For N=32: game 1 is 1v32, game 2 is 16v17, game 3 is 8v25, …
    """
    if num_contestants < 2 or num_contestants & (num_contestants - 1):
        raise ValueError("num_contestants must be a power of 2 and at least 2")

    order = [1]
    while len(order) < num_contestants:
        n = len(order) * 2
        order = [s for x in order for s in (x, n + 1 - x)]
    return order


def first_round_seed_pairs(num_contestants: int) -> list[tuple[int, int]]:
    """(seed, seed) for each first-round tree position 1 .. N/2."""
    order = bracket_seed_order(num_contestants)
    return [(order[i], order[i + 1]) for i in range(0, len(order), 2)]
