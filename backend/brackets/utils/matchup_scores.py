"""Matchup score legs (1- or 2-leg aggregates) for knockout result entry."""

from __future__ import annotations

from typing import Any


def normalize_legs(raw: Any, *, expected_legs: int) -> list[list[int | None]]:
    """
    Parse ``legs`` as ``[[c1, c2], ...]`` with length ``expected_legs``.

    Missing / blank scores become ``None``. Both sides of a leg must be set
    together (or both null).
    """
    if expected_legs < 1:
        raise ValueError("expected_legs must be at least 1")
    if raw is None:
        return [[None, None] for _ in range(expected_legs)]
    if not isinstance(raw, list):
        raise ValueError("scores.legs must be a list")
    if len(raw) != expected_legs:
        raise ValueError(f"Provide exactly {expected_legs} leg score pairs.")

    out: list[list[int | None]] = []
    for i, pair in enumerate(raw):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"Leg {i + 1} must be [score1, score2].")
        parsed: list[int | None] = []
        for side, val in enumerate(pair):
            if val is None or val == "":
                parsed.append(None)
                continue
            try:
                n = int(val)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"Leg {i + 1} score must be a whole number."
                ) from e
            if n < 0:
                raise ValueError("Scores cannot be negative.")
            if n > 99:
                raise ValueError("Scores must be 99 or less.")
            parsed.append(n)
        if (parsed[0] is None) != (parsed[1] is None):
            raise ValueError(
                f"Leg {i + 1} needs both scores, or leave both empty."
            )
        out.append(parsed)
    return out


def aggregate_totals(legs: list[list[int | None]]) -> tuple[int | None, int | None]:
    """Sum completed legs; None if no leg is fully scored."""
    t1 = 0
    t2 = 0
    any_complete = False
    for a, b in legs:
        if a is None or b is None:
            continue
        any_complete = True
        t1 += a
        t2 += b
    if not any_complete:
        return None, None
    return t1, t2


def winner_id_from_totals(
    contestant1_id: int | None,
    contestant2_id: int | None,
    total1: int | None,
    total2: int | None,
) -> int | None:
    if (
        contestant1_id is None
        or contestant2_id is None
        or total1 is None
        or total2 is None
    ):
        return None
    if total1 > total2:
        return contestant1_id
    if total2 > total1:
        return contestant2_id
    return None


def scores_public(legs: list[list[int | None]]) -> dict[str, Any]:
    t1, t2 = aggregate_totals(legs)
    return {
        "legs": legs,
        "total1": t1,
        "total2": t2,
    }
