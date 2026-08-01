"""
Group-stage fixtures and standings (PTS / GD / GS / GC).

Fixtures live on ``UserBracket.metadata["group_fixtures"]``. Completed results
drive ``group_positions`` so existing KO sync stays unchanged.
"""

from __future__ import annotations

from typing import Any


def generate_round_robin(
    team_ids: list[int],
    *,
    matches_per_contestant: int,
    group_code: str = "A",
) -> list[dict[str, Any]]:
    """
    Build fixtures for one group.

    - ``matches_per_contestant == n - 1`` → single round-robin
    - ``matches_per_contestant == 2 * (n - 1)`` → home and away
    """
    n = len(team_ids)
    if n < 2:
        return []
    single = n - 1
    double = 2 * (n - 1)
    if matches_per_contestant not in (single, double):
        raise ValueError(
            f"matches_per_contestant must be {single} (single) or "
            f"{double} (home & away) for a group of {n}."
        )
    double_rr = matches_per_contestant == double
    fixtures: list[dict[str, Any]] = []
    idx = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = team_ids[i], team_ids[j]
            fixtures.append(
                {
                    "id": f"{group_code}-{idx}",
                    "home_id": a,
                    "away_id": b,
                    "home_score": None,
                    "away_score": None,
                }
            )
            idx += 1
            if double_rr:
                fixtures.append(
                    {
                        "id": f"{group_code}-{idx}",
                        "home_id": b,
                        "away_id": a,
                        "home_score": None,
                        "away_score": None,
                    }
                )
                idx += 1
    return fixtures


def ensure_group_fixtures(
    preview: list[dict[str, Any]],
    existing: dict[str, Any] | None,
    *,
    matches_per_contestant: int,
) -> dict[str, list[dict[str, Any]]]:
    """
    Return fixtures for every group, generating missing groups and preserving
    scores when the team set / schedule shape still matches.
    """
    existing = existing if isinstance(existing, dict) else {}
    out: dict[str, list[dict[str, Any]]] = {}
    for g in preview:
        code = g["code"]
        team_ids = [int(t["id"]) for t in g["teams"]]
        generated = generate_round_robin(
            team_ids,
            matches_per_contestant=matches_per_contestant,
            group_code=code,
        )
        prev = existing.get(code)
        if not isinstance(prev, list) or len(prev) != len(generated):
            out[code] = generated
            continue
        # Preserve scores when pairings match by id/home/away.
        by_key = {}
        for row in prev:
            if not isinstance(row, dict):
                continue
            key = (row.get("home_id"), row.get("away_id"), row.get("id"))
            by_key[key] = row
        merged: list[dict[str, Any]] = []
        for row in generated:
            key = (row["home_id"], row["away_id"], row["id"])
            old = by_key.get(key)
            if old is None:
                # try without id
                for (h, a, _), cand in by_key.items():
                    if h == row["home_id"] and a == row["away_id"]:
                        old = cand
                        break
            if old is not None:
                hs = old.get("home_score")
                aws = old.get("away_score")
                merged.append(
                    {
                        **row,
                        "home_score": hs if hs is not None and hs != "" else None,
                        "away_score": aws if aws is not None and aws != "" else None,
                    }
                )
            else:
                merged.append(row)
        out[code] = merged
    return out


def _parse_score(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        n = int(val)
    except (TypeError, ValueError) as e:
        raise ValueError("Match scores must be whole numbers.") from e
    if n < 0:
        raise ValueError("Match scores cannot be negative.")
    if n > 99:
        raise ValueError("Match scores must be 99 or less.")
    return n


def sanitize_group_fixtures(
    preview: list[dict[str, Any]],
    raw: Any,
) -> dict[str, list[dict[str, Any]]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("group_fixtures must be an object")
    code_to_ids = {g["code"]: {int(t["id"]) for t in g["teams"]} for g in preview}
    out: dict[str, list[dict[str, Any]]] = {}
    for code, rows in raw.items():
        if code not in code_to_ids:
            raise ValueError(f"Unknown group code in fixtures: {code}")
        if not isinstance(rows, list):
            raise ValueError(f"Fixtures for group {code} must be a list")
        allowed = code_to_ids[code]
        cleaned: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"Fixture {i} in group {code} must be an object")
            try:
                home_id = int(row["home_id"])
                away_id = int(row["away_id"])
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError(
                    f"Fixture {i} in group {code} needs home_id and away_id."
                ) from e
            if home_id not in allowed or away_id not in allowed:
                raise ValueError(
                    f"Fixture teams must belong to group {code}."
                )
            if home_id == away_id:
                raise ValueError("A team cannot play itself.")
            hs = _parse_score(row.get("home_score"))
            aws = _parse_score(row.get("away_score"))
            if (hs is None) != (aws is None):
                raise ValueError(
                    f"Fixture in group {code} needs both scores or neither."
                )
            fid = str(row.get("id") or f"{code}-{i}")
            cleaned.append(
                {
                    "id": fid,
                    "home_id": home_id,
                    "away_id": away_id,
                    "home_score": hs,
                    "away_score": aws,
                }
            )
        out[code] = cleaned
    return out


def standings_for_group(
    team_ids: list[int],
    fixtures: list[dict[str, Any]],
    *,
    points_per_win: int = 3,
    points_per_tie: int = 1,
    points_per_loss: int = 0,
) -> list[dict[str, Any]]:
    """
    Rank teams by PTS, then GD, then GS (goals scored).

    Each row: contestant_id, played, w, d, l, gf, ga, gd, pts
    """
    stats: dict[int, dict[str, int]] = {
        tid: {
            "played": 0,
            "w": 0,
            "d": 0,
            "l": 0,
            "gf": 0,
            "ga": 0,
            "pts": 0,
        }
        for tid in team_ids
    }
    for row in fixtures:
        hs = row.get("home_score")
        aws = row.get("away_score")
        if hs is None or aws is None:
            continue
        home = int(row["home_id"])
        away = int(row["away_id"])
        if home not in stats or away not in stats:
            continue
        hs_i = int(hs)
        aws_i = int(aws)
        stats[home]["played"] += 1
        stats[away]["played"] += 1
        stats[home]["gf"] += hs_i
        stats[home]["ga"] += aws_i
        stats[away]["gf"] += aws_i
        stats[away]["ga"] += hs_i
        if hs_i > aws_i:
            stats[home]["w"] += 1
            stats[away]["l"] += 1
            stats[home]["pts"] += points_per_win
            stats[away]["pts"] += points_per_loss
        elif hs_i < aws_i:
            stats[away]["w"] += 1
            stats[home]["l"] += 1
            stats[away]["pts"] += points_per_win
            stats[home]["pts"] += points_per_loss
        else:
            stats[home]["d"] += 1
            stats[away]["d"] += 1
            stats[home]["pts"] += points_per_tie
            stats[away]["pts"] += points_per_tie

    rows: list[dict[str, Any]] = []
    for tid in team_ids:
        s = stats[tid]
        gd = s["gf"] - s["ga"]
        rows.append(
            {
                "contestant_id": tid,
                "played": s["played"],
                "w": s["w"],
                "d": s["d"],
                "l": s["l"],
                "gf": s["gf"],
                "ga": s["ga"],
                "gd": gd,
                "pts": s["pts"],
            }
        )
    rows.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["contestant_id"]))
    return rows


def positions_from_standings(
    standings: list[dict[str, Any]],
) -> dict[str, int]:
    """Map rank string → contestant_id (1-based)."""
    return {
        str(i + 1): int(row["contestant_id"])
        for i, row in enumerate(standings)
    }


def group_positions_from_fixtures(
    preview: list[dict[str, Any]],
    fixtures_by_group: dict[str, list[dict[str, Any]]],
    *,
    points_per_win: int = 3,
    points_per_tie: int = 1,
    points_per_loss: int = 0,
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for g in preview:
        code = g["code"]
        team_ids = [int(t["id"]) for t in g["teams"]]
        fixtures = fixtures_by_group.get(code) or []
        standings = standings_for_group(
            team_ids,
            fixtures,
            points_per_win=points_per_win,
            points_per_tie=points_per_tie,
            points_per_loss=points_per_loss,
        )
        out[code] = positions_from_standings(standings)
    return out


def group_fixtures_complete(fixtures: list[dict[str, Any]] | None) -> bool:
    """True when the group has at least one fixture and every score is set."""
    if not fixtures:
        return False
    for row in fixtures:
        if not isinstance(row, dict):
            return False
        if row.get("home_score") is None or row.get("away_score") is None:
            return False
    return True


def completed_group_codes_from_fixtures(
    preview: list[dict[str, Any]],
    fixtures_by_group: dict[str, Any] | None,
) -> set[str]:
    fixtures_by_group = fixtures_by_group if isinstance(fixtures_by_group, dict) else {}
    done: set[str] = set()
    for g in preview:
        code = g["code"]
        rows = fixtures_by_group.get(code)
        if group_fixtures_complete(rows if isinstance(rows, list) else None):
            done.add(code)
    return done
