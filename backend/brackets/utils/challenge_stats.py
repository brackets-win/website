"""Aggregate pick statistics for a bracket challenge."""

from __future__ import annotations

from typing import Any

from brackets.api.serializers import bracket_groups_preview, contestant_public
from brackets.models import (
    Bracket,
    BracketChallenge,
    BracketContestant,
    BracketStage,
    GroupStage,
    KnockoutStage,
    UserBracket,
)
from brackets.utils.sync_group_knockout import (
    contestants_credited_for_knockout_score,
    contestants_in_stage_for_scoring,
)

# "entries" revision: bumped when a challenge entry changes (submit/edit/delete).
# Controls the master-independent part of stats (Teams section + group avg place).
CHALLENGE_STATS_REVISION_KEY = "challenge_stats_revision"
CHALLENGE_STATS_CACHE_KEY = "challenge_stats_cache"
# "master" revision: bumped when the master bracket / results change. Only the
# group points block (max/avg points, difficulty) depends on the master.
CHALLENGE_STATS_MASTER_REVISION_KEY = "challenge_stats_master_revision"
CHALLENGE_STATS_POINTS_CACHE_KEY = "challenge_stats_points_cache"


def get_challenge_stats_revision(challenge: BracketChallenge) -> int:
    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    return int(meta.get(CHALLENGE_STATS_REVISION_KEY) or 0)


def get_challenge_stats_master_revision(challenge: BracketChallenge) -> int:
    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    return int(meta.get(CHALLENGE_STATS_MASTER_REVISION_KEY) or 0)


def bump_challenge_stats_revision(challenge: BracketChallenge) -> int:
    """Entry changed: invalidate the master-independent stats (and points)."""
    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    revision = int(meta.get(CHALLENGE_STATS_REVISION_KEY) or 0) + 1
    meta[CHALLENGE_STATS_REVISION_KEY] = revision
    # The points block depends on entries too, so it is now stale as well.
    meta.pop(CHALLENGE_STATS_CACHE_KEY, None)
    meta.pop(CHALLENGE_STATS_POINTS_CACHE_KEY, None)
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])
    return revision


def bump_challenge_stats_master_revision(challenge: BracketChallenge) -> int:
    """Master changed: only the group points block needs recompute."""
    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    revision = int(meta.get(CHALLENGE_STATS_MASTER_REVISION_KEY) or 0) + 1
    meta[CHALLENGE_STATS_MASTER_REVISION_KEY] = revision
    meta.pop(CHALLENGE_STATS_POINTS_CACHE_KEY, None)
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])
    return revision


def bump_challenge_stats_for_bracket(bracket: Bracket) -> None:
    """Master results change: only the group points block is affected."""
    for challenge in BracketChallenge.objects.filter(bracket=bracket).only(
        "id", "metadata"
    ):
        bump_challenge_stats_master_revision(challenge)


def bump_challenge_stats_full_for_bracket(bracket: Bracket) -> None:
    """Structural/scoring change: invalidate every cached part."""
    for challenge in BracketChallenge.objects.filter(bracket=bracket).only(
        "id", "metadata"
    ):
        bump_challenge_stats_revision(challenge)
        bump_challenge_stats_master_revision(challenge)


def invalidate_challenge_stats_for_user_bracket(ub: UserBracket) -> None:
    """Drop cached stats after a challenge entry or master bracket changes."""
    if ub.challenge_id is not None:
        challenge = BracketChallenge.objects.filter(pk=ub.challenge_id).first()
        if challenge is not None:
            bump_challenge_stats_revision(challenge)
        return
    if ub.is_master:
        bump_challenge_stats_for_bracket(ub.bracket)


def _read_entries_cache(
    challenge: BracketChallenge, revision: int
) -> dict[str, Any] | None:
    """Master-independent part: submitted count, group teams, knockout."""
    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    cache = meta.get(CHALLENGE_STATS_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    if cache.get("revision") != revision:
        return None
    submitted_count = cache.get("submitted_count")
    group_teams = cache.get("group_teams")
    knockout = cache.get("knockout")
    bracket = cache.get("bracket")
    if (
        not isinstance(submitted_count, int)
        or not isinstance(group_teams, list)
        or not isinstance(knockout, dict)
        # Older caches predate the bracket pick-distribution block; recompute.
        or not isinstance(bracket, dict)
    ):
        return None
    # Older caches stored the whole blob under "group_stage"; force recompute.
    knockout_rows = knockout.get("rows")
    if (
        isinstance(knockout_rows, list)
        and knockout_rows
        and "progression" not in knockout_rows[0]
    ):
        return None
    # Older caches labeled top placements by round ("Final"); the current format
    # uses placement names (Runner-Up, Third/Fourth Place). Force a recompute so
    # stale labels don't linger after deploy.
    if isinstance(knockout_rows, list) and any(
        bucket.get("label") == "Final"
        for row in knockout_rows
        for bucket in row.get("progression", [])
    ):
        return None
    # Knockout-only brackets must not show the seeded first round or a Group
    # Winner column. Older caches predate those changes; force a recompute when
    # either stale column lingers.
    bracket_obj = challenge.bracket
    if not bracket_obj.stages.filter(
        stage_type=BracketStage.StageType.GROUP
    ).exists():
        col_keys = {col.get("key") for col in knockout.get("columns", [])}
        if "group_winner" in col_keys:
            return None
        first_ko = (
            bracket_obj.stages.filter(
                stage_type=BracketStage.StageType.KNOCKOUT
            )
            .order_by("order")
            .first()
        )
        if first_ko is not None and f"stage:{first_ko.id}" in col_keys:
            return None
    return {
        "submitted_count": submitted_count,
        "group_teams": group_teams,
        "knockout": knockout,
        "bracket": bracket,
    }


def _read_points_cache(
    challenge: BracketChallenge,
    entries_revision: int,
    master_revision: int,
) -> dict[str, Any] | None:
    """Group points block, valid only for a given (entries, master) revision."""
    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    cache = meta.get(CHALLENGE_STATS_POINTS_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    if cache.get("entries_revision") != entries_revision:
        return None
    if cache.get("master_revision") != master_revision:
        return None
    group_points = cache.get("group_points")
    if not isinstance(group_points, list):
        return None
    return {"group_points": group_points}


def _write_entries_cache(
    challenge: BracketChallenge,
    revision: int,
    entries_part: dict[str, Any],
) -> None:
    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    meta[CHALLENGE_STATS_CACHE_KEY] = {
        "revision": revision,
        "submitted_count": entries_part["submitted_count"],
        "group_teams": entries_part["group_teams"],
        "knockout": entries_part["knockout"],
        "bracket": entries_part["bracket"],
    }
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])


def _write_points_cache(
    challenge: BracketChallenge,
    entries_revision: int,
    master_revision: int,
    points_part: dict[str, Any],
) -> None:
    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    meta[CHALLENGE_STATS_POINTS_CACHE_KEY] = {
        "entries_revision": entries_revision,
        "master_revision": master_revision,
        "group_points": points_part["group_points"],
    }
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])


def _order_teams_by_master(
    teams: list[dict[str, Any]],
    master_order: list[Any],
) -> list[dict[str, Any]]:
    """Rank teams by the master bracket, keeping avg-place order as fallback.

    ``teams`` arrives pre-sorted by average placement, so unranked teams (or an
    unfilled master group) keep that order.
    """
    if not master_order:
        return teams
    rank: dict[int, int] = {}
    for idx, team_id in enumerate(master_order):
        try:
            rank[int(team_id)] = idx
        except (TypeError, ValueError):
            continue
    if not rank:
        return teams
    fallback = len(rank)
    return [
        team
        for _, team in sorted(
            enumerate(teams),
            key=lambda it: (
                rank.get(int(it[1]["bracket_contestant_id"]), fallback),
                it[0],
            ),
        )
    ]


def _merge_stats_parts(
    entries_part: dict[str, Any],
    points_part: dict[str, Any],
) -> dict[str, Any]:
    points_by_code = {p["code"]: p for p in points_part["group_points"]}
    group_stage: list[dict[str, Any]] = []
    for group in entries_part["group_teams"]:
        code = group["code"]
        points = points_by_code.get(code, {})
        group_stage.append(
            {
                "code": code,
                "teams": _order_teams_by_master(
                    group["teams"], points.get("master_order") or []
                ),
                "max_points": points.get("max_points", 0),
                "avg_points": points.get("avg_points"),
                "entries": points.get("entries", []),
            }
        )
    return {
        "submitted_count": entries_part["submitted_count"],
        "group_stage": group_stage,
        "knockout": entries_part["knockout"],
        "bracket": entries_part["bracket"],
    }


def get_challenge_stats(challenge: BracketChallenge) -> dict[str, Any]:
    if challenge.pk is not None:
        challenge.refresh_from_db(fields=["metadata"])
    entries_revision = get_challenge_stats_revision(challenge)
    master_revision = get_challenge_stats_master_revision(challenge)

    entries_part = _read_entries_cache(challenge, entries_revision)
    points_part = _read_points_cache(
        challenge, entries_revision, master_revision
    )

    if entries_part is None:
        # Entry data changed: recompute both parts together (shared work).
        entries_part, points_part = _compute_stats_parts(challenge)
        _write_entries_cache(challenge, entries_revision, entries_part)
        _write_points_cache(
            challenge, entries_revision, master_revision, points_part
        )
    elif points_part is None:
        # Only the master changed: recompute the cheaper points block.
        points_part = _compute_points_part(challenge)
        _write_points_cache(
            challenge, entries_revision, master_revision, points_part
        )

    return _merge_stats_parts(entries_part, points_part)


def _team_position_in_row(row: dict, team_id: int) -> int | None:
    if not isinstance(row, dict):
        return None
    for key, cid in row.items():
        if cid is None:
            continue
        try:
            if int(cid) != team_id:
                continue
            return int(key)
        except (TypeError, ValueError):
            continue
    return None


def _row_contestant_at(row: Any, pos: Any) -> int | None:
    """Read the contestant id at a position, tolerating int/str position keys."""
    if not isinstance(row, dict):
        return None
    cid = row.get(pos)
    if cid is None:
        cid = row.get(str(pos))
    if cid is None:
        try:
            cid = row.get(int(pos))
        except (TypeError, ValueError):
            cid = None
    if cid is None:
        return None
    try:
        return int(cid)
    except (TypeError, ValueError):
        return None


def _group_exact_placement_points(
    user_row: Any,
    master_row: Any,
    points_per_exact_position: int,
) -> int:
    """Points an entry earns for exact group placements vs the master."""
    if (
        points_per_exact_position <= 0
        or not isinstance(user_row, dict)
        or not isinstance(master_row, dict)
    ):
        return 0
    total = 0
    for pos, user_cid in user_row.items():
        if user_cid is None:
            continue
        try:
            user_id = int(user_cid)
        except (TypeError, ValueError):
            continue
        master_id = _row_contestant_at(master_row, pos)
        if master_id is not None and master_id == user_id:
            total += points_per_exact_position
    return total


def _progression_scores_for_user_bracket(
    ub: UserBracket,
    *,
    groups_preview: list[dict[str, Any]],
    main_knockout_stages: list[BracketStage],
    third_place_stage: BracketStage | None,
    ub_hits: dict[str, set[int]],
) -> dict[int, int]:
    """Team -> progression score for one submitted user bracket."""
    scores: dict[int, int] = {}
    meta = ub.metadata if isinstance(ub.metadata, dict) else {}
    group_positions = meta.get("group_positions") or {}
    group_sizes = {
        g["code"]: len(g.get("teams") or [])
        for g in groups_preview
    }

    # Group stage scoring: last=0, second-last=1, ... first=(size-1).
    for code, row in group_positions.items():
        if not isinstance(row, dict):
            continue
        size = group_sizes.get(code)
        if size is None or size <= 0:
            continue
        for raw_pos, raw_team_id in row.items():
            if raw_team_id is None:
                continue
            try:
                pos = int(raw_pos)
                team_id = int(raw_team_id)
            except (TypeError, ValueError):
                continue
            points = max(0, size - pos)
            if points <= 0:
                continue
            scores[team_id] = scores.get(team_id, 0) + points

    # Each knockout round (past the seeded first round) is worth more than the
    # last, so deeper advancement always scores higher. The first round is
    # skipped: for group → knockout it reflects group results, and for
    # knockout-only it is admin-seeded.
    has_group_stage = len(groups_preview) > 0
    round_bonus = 3 if has_group_stage else 1
    final_round_bonus = round_bonus
    for stage in main_knockout_stages[1:]:
        for team_id in ub_hits.get(f"stage:{stage.id}", set()):
            scores[team_id] = scores.get(team_id, 0) + round_bonus
        final_round_bonus = round_bonus
        round_bonus += 1

    if third_place_stage is not None:
        tp = ub.matchup_set.filter(stage=third_place_stage, position=1).first()
        if tp is not None and tp.winner_id is not None:
            winner_id = int(tp.winner_id)
            # Rank the third-place winner above fourth place but below the
            # finalists, whatever the bracket size.
            third_place_bonus = (
                3 if has_group_stage else max(1, final_round_bonus - 1)
            )
            scores[winner_id] = scores.get(winner_id, 0) + third_place_bonus

    return scores


class _GroupPointsContext:
    """Shared inputs for per-group points: scoring config + master results."""

    def __init__(
        self,
        *,
        points_per_exact_position: int,
        first_ko_stage: BracketStage | None,
        first_ko_points: int,
        master_gp: dict[str, Any],
        master_first_ko_ids: set[int],
        entry_first_ko_ids: dict[int, set[int]],
    ) -> None:
        self.points_per_exact_position = points_per_exact_position
        self.first_ko_stage = first_ko_stage
        self.first_ko_points = first_ko_points
        self.master_gp = master_gp
        self.master_first_ko_ids = master_first_ko_ids
        self.entry_first_ko_ids = entry_first_ko_ids


def _build_group_points_context(
    bracket: Bracket,
    user_brackets: list[UserBracket],
) -> _GroupPointsContext:
    group_cfg = (
        GroupStage.objects.filter(bracket=bracket).order_by("order").first()
    )
    points_per_exact_position = (
        group_cfg.points_per_exact_position if group_cfg is not None else 0
    )

    first_ko_stage = (
        KnockoutStage.objects.filter(bracket=bracket)
        .exclude(is_third_place=True)
        .order_by("order")
        .first()
    )
    first_ko_points = (
        first_ko_stage.points_per_correct_pick if first_ko_stage is not None else 0
    )

    master = bracket.userbracket_set.filter(is_master=True).first()
    master_gp = {}
    master_first_ko_ids: set[int] = set()
    if master is not None:
        master_gp = (master.metadata or {}).get("group_positions") or {}
        if first_ko_stage is not None:
            master_first_ko_ids = contestants_credited_for_knockout_score(
                master, first_ko_stage
            )

    entry_first_ko_ids: dict[int, set[int]] = {}
    if first_ko_stage is not None:
        for ub in user_brackets:
            entry_first_ko_ids[ub.id] = contestants_credited_for_knockout_score(
                ub, first_ko_stage
            )

    return _GroupPointsContext(
        points_per_exact_position=points_per_exact_position,
        first_ko_stage=first_ko_stage,
        first_ko_points=first_ko_points,
        master_gp=master_gp if isinstance(master_gp, dict) else {},
        master_first_ko_ids=master_first_ko_ids,
        entry_first_ko_ids=entry_first_ko_ids,
    )


def _entry_label(ub: UserBracket) -> str:
    name = (ub.display_name or "").strip()
    if name:
        return name
    return getattr(ub.user, "username", "") or "Player"


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _knockout_progression_for_contestant(
    cid: int,
    user_brackets: list[UserBracket],
    ub_stage_hits: dict[int, dict[str, set[int]]],
    ko_levels: list[tuple[str, str, str]],
    group_code_by_team: dict[int, str],
) -> list[dict[str, Any]]:
    """Buckets of entries by the farthest stage they placed this contestant.

    Ordered farthest-first using ``ko_levels`` (Champions, Runner-Up, then
    Third/Fourth Place or Semi Final, then deeper rounds by name), followed by
    exact group placements for entries that never advanced. Buckets with no
    entries are omitted.
    """
    buckets: dict[str, dict[str, Any]] = {}

    def ensure(key: str, label: str, order: int) -> dict[str, Any]:
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {"key": key, "label": label, "order": order, "entries": []}
            buckets[key] = bucket
        return bucket

    for ub in user_brackets:
        hits = ub_stage_hits.get(ub.id, {})
        bucket: dict[str, Any] | None = None
        for idx, (key, label, hit_key) in enumerate(ko_levels):
            if cid in hits.get(hit_key, set()):
                bucket = ensure(key, label, idx)
                break
        if bucket is None:
            code = group_code_by_team.get(cid)
            if code is not None:
                gp = (ub.metadata or {}).get("group_positions") or {}
                row = gp.get(code) if isinstance(gp, dict) else None
                pos = (
                    _team_position_in_row(row, cid)
                    if isinstance(row, dict)
                    else None
                )
                if pos is not None:
                    bucket = ensure(
                        f"group:{pos}",
                        f"{_ordinal(pos)} in Group",
                        1000 + pos,
                    )
        if bucket is None:
            continue
        bucket["entries"].append(
            {
                "user_bracket_id": ub.id,
                "display_name": _entry_label(ub),
                "username": getattr(ub.user, "username", "") or "",
            }
        )

    ordered = sorted(buckets.values(), key=lambda b: b["order"])
    for bucket in ordered:
        bucket["entries"].sort(key=lambda e: e["display_name"].casefold())
        bucket.pop("order", None)
    return ordered


def _group_points_breakdown(
    group: dict[str, Any],
    user_brackets: list[UserBracket],
    ctx: _GroupPointsContext,
) -> tuple[int, float | None, list[dict[str, Any]]]:
    """Max points, average earned, and per-entry points for one group."""
    code = group["code"]
    group_team_ids = {int(t["id"]) for t in group["teams"]}

    advancers_in_group = ctx.master_first_ko_ids & group_team_ids
    max_points = (
        len(group_team_ids) * ctx.points_per_exact_position
        + len(advancers_in_group) * ctx.first_ko_points
    )

    entries: list[dict[str, Any]] = []
    for ub in user_brackets:
        gp = ub.metadata if isinstance(ub.metadata, dict) else {}
        user_gp = gp.get("group_positions") or {}
        user_row = user_gp.get(code) if isinstance(user_gp, dict) else None
        master_row = ctx.master_gp.get(code)

        points = _group_exact_placement_points(
            user_row, master_row, ctx.points_per_exact_position
        )

        if ctx.first_ko_points > 0 and ctx.first_ko_stage is not None:
            credited = (
                ctx.entry_first_ko_ids.get(ub.id, set())
                & ctx.master_first_ko_ids
                & group_team_ids
            )
            points += len(credited) * ctx.first_ko_points

        entries.append(
            {
                "user_bracket_id": ub.id,
                "display_name": _entry_label(ub),
                "username": getattr(ub.user, "username", "") or "",
                "points": points,
            }
        )

    entries.sort(
        key=lambda e: (-e["points"], e["display_name"].casefold())
    )

    avg_points = (
        round(sum(e["points"] for e in entries) / len(entries), 2)
        if entries
        else None
    )

    return max_points, avg_points, entries


def _submitted_user_brackets(challenge: BracketChallenge) -> list[UserBracket]:
    return list(
        UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            submitted_at__isnull=False,
        )
        .select_related("user")
        .prefetch_related("matchup_set__stage")
    )


def _master_group_order_ids(master_row: Any) -> list[int]:
    """Team ids for one group ordered by their master-bracket placement.

    Empty when the master hasn't filled out the group, which lets the merge
    step fall back to the average-placement ordering.
    """
    if not isinstance(master_row, dict):
        return []
    placed: list[tuple[int, int]] = []
    for raw_pos, raw_team in master_row.items():
        if raw_team is None:
            continue
        try:
            pos = int(raw_pos)
            team_id = int(raw_team)
        except (TypeError, ValueError):
            continue
        placed.append((pos, team_id))
    placed.sort(key=lambda pt: pt[0])
    return [team_id for _, team_id in placed]


def _compute_group_points(
    bracket: Bracket,
    groups_preview: list[dict[str, Any]],
    user_brackets: list[UserBracket],
) -> list[dict[str, Any]]:
    """Per-group max/avg/per-entry points (depends on entries AND master)."""
    ctx = _build_group_points_context(bracket, user_brackets)
    group_points: list[dict[str, Any]] = []
    for group in groups_preview:
        max_points, avg_points, entries = _group_points_breakdown(
            group, user_brackets, ctx
        )
        group_points.append(
            {
                "code": group["code"],
                "max_points": max_points,
                "avg_points": avg_points,
                "entries": entries,
                "master_order": _master_group_order_ids(
                    ctx.master_gp.get(group["code"])
                ),
            }
        )
    return group_points


def _compute_points_part(challenge: BracketChallenge) -> dict[str, Any]:
    bracket = challenge.bracket
    groups_preview = bracket_groups_preview(bracket)
    user_brackets = _submitted_user_brackets(challenge)
    return {
        "group_points": _compute_group_points(
            bracket, groups_preview, user_brackets
        )
    }


def _compute_bracket_slots(
    user_brackets: list[UserBracket],
    *,
    knockout_stages: list[BracketStage],
    final_stage: KnockoutStage | None,
    third_place_stage: BracketStage | None,
    contestant_info: dict[int, dict[str, Any]],
    submitted_count: int,
) -> dict[str, Any]:
    """Pick distribution for each knockout bracket slot across submitted entries.

    Slots are keyed ``"{stage_id}:{position}:{side}"`` where ``side`` is ``1`` for
    a matchup's first contestant and ``2`` for its second, mirroring how the
    bracket UI splits each box. The champion (final winner) is keyed ``champion``
    and the third-place winner ``third_place``. Depends only on submitted entries
    (not the master), so this lives in the entries cache and recomputes when a
    bracket is submitted or edited.
    """
    knockout_stage_ids = {s.id for s in knockout_stages}
    final_stage_id = final_stage.id if final_stage is not None else None
    third_place_stage_id = (
        third_place_stage.id if third_place_stage is not None else None
    )

    counts: dict[str, dict[int, int]] = {}

    def add(key: str, cid: int | None) -> None:
        if cid is None:
            return
        bucket = counts.setdefault(key, {})
        bucket[cid] = bucket.get(cid, 0) + 1

    for ub in user_brackets:
        for m in ub.matchup_set.all():
            if m.stage_id not in knockout_stage_ids:
                continue
            add(f"{m.stage_id}:{m.position}:1", m.contestant1_id)
            add(f"{m.stage_id}:{m.position}:2", m.contestant2_id)
            if final_stage_id is not None and m.stage_id == final_stage_id:
                add("champion", m.winner_id)
            if (
                third_place_stage_id is not None
                and m.stage_id == third_place_stage_id
            ):
                add("third_place", m.winner_id)

    slots: dict[str, list[dict[str, Any]]] = {}
    for key, bucket in counts.items():
        entries: list[dict[str, Any]] = []
        for cid, count in bucket.items():
            info = contestant_info.get(cid)
            if info is None:
                continue
            entries.append(
                {
                    "bracket_contestant_id": cid,
                    "display_name": info["display_name"],
                    "image_url": info["image_url"],
                    "count": count,
                    "pct": round(100.0 * count / submitted_count, 1)
                    if submitted_count > 0
                    else 0.0,
                }
            )
        entries.sort(key=lambda e: (-e["count"], e["display_name"].casefold()))
        if entries:
            slots[key] = entries

    return {"slots": slots}


def compute_challenge_stats(challenge: BracketChallenge) -> dict[str, Any]:
    entries_part, points_part = _compute_stats_parts(challenge)
    return _merge_stats_parts(entries_part, points_part)


def _compute_stats_parts(
    challenge: BracketChallenge,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bracket = challenge.bracket
    groups_preview = bracket_groups_preview(bracket)

    user_brackets = _submitted_user_brackets(challenge)
    submitted_count = len(user_brackets)

    group_points = _compute_group_points(bracket, groups_preview, user_brackets)

    group_teams: list[dict[str, Any]] = []
    for group in groups_preview:
        code = group["code"]
        teams_out: list[dict[str, Any]] = []
        for team in group["teams"]:
            team_id = int(team["id"])
            positions: list[int] = []
            for ub in user_brackets:
                gp = (ub.metadata or {}).get("group_positions") or {}
                row = gp.get(code)
                pos = _team_position_in_row(row, team_id) if isinstance(row, dict) else None
                if pos is not None:
                    positions.append(pos)
            avg = (
                round(sum(positions) / len(positions), 2)
                if positions
                else None
            )
            teams_out.append(
                {
                    "bracket_contestant_id": team_id,
                    "display_name": team["display_name"],
                    "image_url": team.get("image_url"),
                    "average_position": avg,
                    "pick_count": len(positions),
                }
            )
        teams_out.sort(
            key=lambda t: (
                t["average_position"] is None,
                t["average_position"] if t["average_position"] is not None else 999.0,
            )
        )
        group_teams.append({"code": code, "teams": teams_out})

    knockout_stages = list(
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT).order_by(
            "order"
        )
    )
    # Knockout-only brackets seed the first round, so its percentages are always
    # 100% and carry no information — drop that column. Group → knockout brackets
    # keep it: the first round reflects who advanced from the group stage.
    has_group_stage = len(groups_preview) > 0
    hidden_stage_id = (
        knockout_stages[0].id
        if knockout_stages and not has_group_stage
        else None
    )
    stage_columns = [
        {"key": f"stage:{stage.id}", "name": stage.name}
        for stage in reversed(knockout_stages)
        if stage.id != hidden_stage_id
    ]
    columns = [
        {"key": "progression_score", "name": "PROGRESSION SCORE"},
        {"key": "champion", "name": "Champions"},
        {"key": "runner_up", "name": "Runner-up"},
        *stage_columns,
        # Group Winner only applies when the bracket has a group stage.
        *(
            [{"key": "group_winner", "name": "Group Winner"}]
            if has_group_stage
            else []
        ),
    ]

    final_stage = KnockoutStage.objects.filter(
        bracket=bracket, is_final=True
    ).first()
    third_place_ids = {
        ks.pk
        for ks in KnockoutStage.objects.filter(
            bracket=bracket,
            is_third_place=True,
        )
    }
    third_place_stage = next(
        (s for s in knockout_stages if s.id in third_place_ids),
        None,
    )
    main_knockout_stages = [s for s in knockout_stages if s.id not in third_place_ids]
    # The main stage immediately before the final (its losers play for 3rd/4th).
    semifinal_stage: BracketStage | None = None
    if final_stage is not None:
        prev: BracketStage | None = None
        for stage in main_knockout_stages:
            if stage.id == final_stage.id:
                semifinal_stage = prev
                break
            prev = stage

    ub_stage_hits: dict[int, dict[str, set[int]]] = {}
    for ub in user_brackets:
        hits: dict[str, set[int]] = {}
        for stage in knockout_stages:
            hits[f"stage:{stage.id}"] = contestants_in_stage_for_scoring(ub, stage)
        champ = ub.get_final_matchup_winner()
        hits["champion"] = {champ.id} if champ is not None else set()
        runner_up: set[int] = set()
        if champ is not None and final_stage is not None:
            final_matchup = ub.matchup_set.filter(stage=final_stage).first()
            if final_matchup is not None:
                loser = final_matchup.get_loser()
                if loser is not None:
                    runner_up = {loser.id}
        hits["runner_up"] = runner_up
        third_place: set[int] = set()
        fourth_place: set[int] = set()
        if third_place_stage is not None:
            tp_matchup = ub.matchup_set.filter(stage=third_place_stage).first()
            if tp_matchup is not None:
                tp_winner = tp_matchup.winner
                if tp_winner is not None:
                    third_place = {tp_winner.id}
                tp_loser = tp_matchup.get_loser()
                if tp_loser is not None:
                    fourth_place = {tp_loser.id}
        hits["third_place"] = third_place
        hits["fourth_place"] = fourth_place
        group_winners: set[int] = set()
        gp = (ub.metadata or {}).get("group_positions") or {}
        for row in gp.values():
            if not isinstance(row, dict):
                continue
            first = row.get("1")
            if first is None:
                continue
            try:
                group_winners.add(int(first))
            except (TypeError, ValueError):
                continue
        hits["group_winner"] = group_winners
        ub_stage_hits[ub.id] = hits

    progression_totals: dict[int, int] = {}
    for ub in user_brackets:
        ub_scores = _progression_scores_for_user_bracket(
            ub,
            groups_preview=groups_preview,
            main_knockout_stages=main_knockout_stages,
            third_place_stage=third_place_stage,
            ub_hits=ub_stage_hits.get(ub.id, {}),
        )
        for team_id, score in ub_scores.items():
            progression_totals[team_id] = progression_totals.get(team_id, 0) + score

    reversed_main_ko_stages = list(reversed(main_knockout_stages))
    # Farthest-first progression levels. The top placements use placement names
    # (Champions, Runner-Up, and Third/Fourth Place when a third-place match
    # exists) rather than round names so each entry lands in exactly one bucket.
    ko_levels: list[tuple[str, str, str]] = [
        ("champion", "Champions", "champion"),
        ("runner_up", "Runner-Up", "runner_up"),
    ]
    if third_place_stage is not None:
        ko_levels.append(("third_place", "Third Place", "third_place"))
        ko_levels.append(("fourth_place", "Fourth Place", "fourth_place"))
    for stage in reversed_main_ko_stages:
        if final_stage is not None and stage.id == final_stage.id:
            continue
        if (
            third_place_stage is not None
            and semifinal_stage is not None
            and stage.id == semifinal_stage.id
        ):
            continue
        ko_levels.append((f"stage:{stage.id}", stage.name, f"stage:{stage.id}"))

    group_code_by_team: dict[int, str] = {}
    for group in groups_preview:
        for team in group["teams"]:
            try:
                group_code_by_team[int(team["id"])] = group["code"]
            except (TypeError, ValueError):
                continue

    knockout_rows: list[dict[str, Any]] = []
    contestant_info: dict[int, dict[str, Any]] = {}
    contestants = (
        BracketContestant.objects.filter(bracket=bracket)
        .select_related("contestant")
        .prefetch_related("contestant__tags")
        .order_by("seed", "id")
    )
    for bc in contestants:
        pub = contestant_public(bc)
        contestant_info[pub["id"]] = {
            "display_name": pub["display_name"],
            "image_url": pub["image_url"],
        }
        percentages: dict[str, float] = {}
        for col in columns:
            key = col["key"]
            if key == "progression_score":
                continue
            if submitted_count == 0:
                percentages[key] = 0.0
                continue
            hits = sum(
                1
                for ub in user_brackets
                if bc.id in ub_stage_hits[ub.id].get(key, set())
            )
            percentages[key] = round(100.0 * hits / submitted_count, 1)
        knockout_rows.append(
            {
                "bracket_contestant_id": pub["id"],
                "display_name": pub["display_name"],
                "image_url": pub["image_url"],
                "progression_score": round(
                    progression_totals.get(pub["id"], 0) / submitted_count, 2
                )
                if submitted_count > 0
                else 0.0,
                "percentages": percentages,
                "progression": _knockout_progression_for_contestant(
                    bc.id,
                    user_brackets,
                    ub_stage_hits,
                    ko_levels,
                    group_code_by_team,
                ),
            }
        )

    bracket_slots = _compute_bracket_slots(
        user_brackets,
        knockout_stages=knockout_stages,
        final_stage=final_stage,
        third_place_stage=third_place_stage,
        contestant_info=contestant_info,
        submitted_count=submitted_count,
    )

    entries_part = {
        "submitted_count": submitted_count,
        "group_teams": group_teams,
        "knockout": {"columns": columns, "rows": knockout_rows},
        "bracket": bracket_slots,
    }
    points_part = {"group_points": group_points}
    return entries_part, points_part
