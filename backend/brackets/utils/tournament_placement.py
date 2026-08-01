"""
Seed placement for tournament rosters (manual / random / random_balanced).

Writes contiguous seeds so ``bracket_groups_preview`` chunks into groups correctly.
Does not create GroupMembership rows.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any


def pot_capacity(total: int, num_pots: int) -> int:
    if num_pots < 1 or total % num_pots != 0:
        raise ValueError("Number of pots must divide the team count evenly.")
    return total // num_pots


def supported_pot_counts(total: int) -> list[int]:
    """Divisors of total in [2, total // 2]."""
    if total < 4:
        return []
    out: list[int] = []
    for d in range(2, total // 2 + 1):
        if total % d == 0:
            out.append(d)
    return out


def _parse_named_teams(teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in teams:
        if not isinstance(row, dict):
            raise ValueError("Each team must be an object with a name.")
        cid_raw = row.get("contestant_id")
        contestant_id: int | None = None
        if cid_raw is not None and str(cid_raw).strip() != "":
            try:
                contestant_id = int(cid_raw)
            except (TypeError, ValueError) as e:
                raise ValueError("contestant_id must be a number.") from e
        name = str(row.get("name") or "").strip()
        if not name and contestant_id is None:
            raise ValueError("Each team needs a name.")
        if not name:
            name = f"Contestant {contestant_id}"
        if len(name) > 100:
            raise ValueError("Team names must be 100 characters or fewer.")
        pot_raw = row.get("pot")
        pot: int | None
        if pot_raw is None or str(pot_raw).strip() == "":
            pot = None
        else:
            try:
                pot = int(pot_raw)
            except (TypeError, ValueError) as e:
                raise ValueError("Pot must be a number.") from e
            if pot < 1:
                raise ValueError("Pot must be at least 1.")
        entry: dict[str, Any] = {"name": name, "pot": pot}
        if contestant_id is not None:
            entry["contestant_id"] = contestant_id
        parsed.append(entry)
    return parsed


def _with_seed(team: dict[str, Any], seed: int) -> dict[str, Any]:
    out: dict[str, Any] = {"name": team["name"], "seed": seed}
    if team.get("contestant_id") is not None:
        out["contestant_id"] = team["contestant_id"]
    return out


def _snake_group_assignment(
    ordered: list[dict[str, Any]],
    num_groups: int,
    teams_per_group: int,
) -> list[dict[str, Any]]:
    """
    Assign ordered teams into group slots via snake, then contiguous seeds.

    Slot order: pot/tier wave 0 → groups 0..G-1 slot 1; wave 1 → G-1..0 slot 2; …
    Seed = group_index * teams_per_group + slot (1-based slot).
    """
    total = num_groups * teams_per_group
    if len(ordered) != total:
        raise ValueError(f"Expected {total} teams for group placement.")

    # slot_map[(group_idx, slot)] = team
    filled: dict[tuple[int, int], dict[str, Any]] = {}
    for i, team in enumerate(ordered):
        wave = i // num_groups
        pos = i % num_groups
        if wave % 2 == 0:
            group_idx = pos
        else:
            group_idx = num_groups - 1 - pos
        slot = wave + 1
        if slot > teams_per_group:
            raise ValueError("Too many teams for group slots.")
        filled[(group_idx, slot)] = team

    out: list[dict[str, Any]] = []
    for g in range(num_groups):
        for slot in range(1, teams_per_group + 1):
            team = filled[(g, slot)]
            seed = g * teams_per_group + slot
            out.append(_with_seed(team, seed))
    return out


def _round_robin_group_assignment(
    shuffled: list[dict[str, Any]],
    num_groups: int,
    teams_per_group: int,
) -> list[dict[str, Any]]:
    total = num_groups * teams_per_group
    if len(shuffled) != total:
        raise ValueError(f"Expected {total} teams for group placement.")

    # Fill group slots in order: A1, B1, C1… then A2, B2…
    by_slot: list[list[dict[str, Any]]] = [[] for _ in range(num_groups)]
    for i, team in enumerate(shuffled):
        by_slot[i % num_groups].append(team)

    out: list[dict[str, Any]] = []
    for g in range(num_groups):
        if len(by_slot[g]) != teams_per_group:
            raise ValueError("Uneven group fill after random draw.")
        for slot, team in enumerate(by_slot[g], start=1):
            seed = g * teams_per_group + slot
            out.append(_with_seed(team, seed))
    return out


def _knockout_seeds_in_order(ordered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_with_seed(team, idx + 1) for idx, team in enumerate(ordered)]


def _order_by_pots(teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shuffle within each pot, then concatenate pots in ascending pot order."""
    by_pot: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for team in teams:
        pot = team.get("pot")
        if pot is None:
            raise ValueError("Each team needs a pot for random balanced draw.")
        by_pot[int(pot)].append(team)

    if not by_pot:
        raise ValueError("No teams to place.")

    pots = sorted(by_pot.keys())
    expected = list(range(1, len(pots) + 1))
    if pots != expected:
        raise ValueError("Pots must be numbered consecutively starting at 1.")

    sizes = [len(by_pot[p]) for p in pots]
    if len(set(sizes)) != 1:
        raise ValueError("Each pot must hold the same number of teams.")

    ordered: list[dict[str, Any]] = []
    for p in pots:
        bucket = list(by_pot[p])
        random.shuffle(bucket)
        ordered.extend(bucket)
    return ordered


def _order_bye_and_play_pots(teams: list[dict[str, Any]], bye_count: int) -> list[dict[str, Any]]:
    """
    Two unequal pots for non-power-of-2 single elim:
    pot 1 = bye seeds 1..byes, pot 2 = play-in seeds byes+1..N.
    """
    by_pot: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for team in teams:
        pot = team.get("pot")
        if pot is None:
            raise ValueError("Each team needs a pot for random balanced draw.")
        by_pot[int(pot)].append(team)

    if sorted(by_pot.keys()) != [1, 2]:
        raise ValueError("Bye draws use two pots: Bye and Round 1.")

    bye_bucket = list(by_pot[1])
    play_bucket = list(by_pot[2])
    play_count = len(teams) - bye_count
    if len(bye_bucket) != bye_count:
        raise ValueError(f"Bye pot must have exactly {bye_count} teams.")
    if len(play_bucket) != play_count:
        raise ValueError(f"Round 1 pot must have exactly {play_count} teams.")

    random.shuffle(bye_bucket)
    random.shuffle(play_bucket)
    return bye_bucket + play_bucket


def compute_draw_seeds(
    *,
    mode: str,
    teams: list[dict[str, Any]],
    structure: str,
    number_of_groups: int | None,
    teams_per_group: int | None,
) -> list[dict[str, Any]]:
    """
    Return ``[{name, seed}, ...]`` for apply_tournament_teams.

    mode: ``random`` | ``random_balanced``
    """
    from brackets.utils.single_elim_byes import (
        is_power_of_2,
        single_elim_bye_count,
        validate_single_elim_roster,
    )

    parsed = _parse_named_teams(teams)
    n = len(parsed)
    if n < 2:
        raise ValueError("Need at least 2 teams.")

    is_gk = structure == "GROUP_KNOCKOUT"
    if is_gk:
        if not number_of_groups or not teams_per_group:
            raise ValueError("Group stage configuration is missing.")
        if number_of_groups * teams_per_group != n:
            raise ValueError(
                f"Provide exactly {number_of_groups * teams_per_group} teams."
            )
    else:
        validate_single_elim_roster(n)

    if mode == "random":
        shuffled = list(parsed)
        random.shuffle(shuffled)
        if is_gk:
            return _round_robin_group_assignment(
                shuffled, number_of_groups, teams_per_group  # type: ignore[arg-type]
            )
        return _knockout_seeds_in_order(shuffled)

    if mode == "random_balanced":
        if not is_gk and not is_power_of_2(n):
            bye_count = single_elim_bye_count(n)
            ordered = _order_bye_and_play_pots(parsed, bye_count)
            return _knockout_seeds_in_order(ordered)
        ordered = _order_by_pots(parsed)
        if is_gk:
            return _snake_group_assignment(
                ordered, number_of_groups, teams_per_group  # type: ignore[arg-type]
            )
        return _knockout_seeds_in_order(ordered)

    raise ValueError("mode must be 'random' or 'random_balanced'.")
