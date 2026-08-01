"""Single-elimination field size and bye math for non-power-of-2 rosters."""

from __future__ import annotations


def is_power_of_2(n: int) -> bool:
    return n >= 2 and (n & (n - 1)) == 0


def next_power_of_2(n: int) -> int:
    """Smallest power of 2 that is >= n (n >= 1)."""
    if n < 1:
        raise ValueError("n must be at least 1")
    p = 1
    while p < n:
        p *= 2
    return p


def validate_single_elim_roster(roster: int) -> None:
    if roster < 2:
        raise ValueError("Single elimination needs at least 2 teams.")
    if roster % 2 != 0:
        raise ValueError("Single elimination team count must be even.")


def single_elim_field_size(roster: int) -> int:
    """Bracket shell size (next power of 2 >= roster)."""
    validate_single_elim_roster(roster)
    return next_power_of_2(roster)


def single_elim_bye_count(roster: int) -> int:
    """How many teams receive a first-round bye (seeds 1 .. byes)."""
    return single_elim_field_size(roster) - roster


def single_elim_play_in_count(roster: int) -> int:
    """How many teams play in the opening round."""
    return roster - single_elim_bye_count(roster)


def roster_size_from_bracket(bracket) -> int | None:
    """Actual entry count for a single-elim bracket, if known."""
    meta = bracket.metadata if isinstance(bracket.metadata, dict) else {}
    raw = meta.get("roster_size")
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if n >= 2 else None
