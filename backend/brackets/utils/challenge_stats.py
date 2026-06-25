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

CHALLENGE_STATS_REVISION_KEY = "challenge_stats_revision"
CHALLENGE_STATS_CACHE_KEY = "challenge_stats_cache"


def get_challenge_stats_revision(challenge: BracketChallenge) -> int:
    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    return int(meta.get(CHALLENGE_STATS_REVISION_KEY) or 0)


def bump_challenge_stats_revision(challenge: BracketChallenge) -> int:
    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    revision = int(meta.get(CHALLENGE_STATS_REVISION_KEY) or 0) + 1
    meta[CHALLENGE_STATS_REVISION_KEY] = revision
    meta.pop(CHALLENGE_STATS_CACHE_KEY, None)
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])
    return revision


def bump_challenge_stats_for_bracket(bracket: Bracket) -> None:
    for challenge in BracketChallenge.objects.filter(bracket=bracket).only(
        "id", "metadata"
    ):
        bump_challenge_stats_revision(challenge)


def invalidate_challenge_stats_for_user_bracket(ub: UserBracket) -> None:
    """Drop cached stats after a challenge entry or master bracket changes."""
    if ub.challenge_id is not None:
        challenge = BracketChallenge.objects.filter(pk=ub.challenge_id).first()
        if challenge is not None:
            bump_challenge_stats_revision(challenge)
        return
    if ub.is_master:
        bump_challenge_stats_for_bracket(ub.bracket)


def _read_cached_stats(
    challenge: BracketChallenge, revision: int
) -> dict[str, Any] | None:
    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    cache = meta.get(CHALLENGE_STATS_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    if cache.get("revision") != revision:
        return None
    submitted_count = cache.get("submitted_count")
    group_stage = cache.get("group_stage")
    knockout = cache.get("knockout")
    if (
        not isinstance(submitted_count, int)
        or not isinstance(group_stage, list)
        or not isinstance(knockout, dict)
    ):
        return None
    # Older caches predate per-group points; force a recompute so the new
    # fields (max_points, avg_points, entries) are present.
    if group_stage and "entries" not in group_stage[0]:
        return None
    return {
        "submitted_count": submitted_count,
        "group_stage": group_stage,
        "knockout": knockout,
    }


def _write_cached_stats(
    challenge: BracketChallenge,
    revision: int,
    stats: dict[str, Any],
) -> None:
    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    meta[CHALLENGE_STATS_CACHE_KEY] = {
        "revision": revision,
        "submitted_count": stats["submitted_count"],
        "group_stage": stats["group_stage"],
        "knockout": stats["knockout"],
    }
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])


def get_challenge_stats(challenge: BracketChallenge) -> dict[str, Any]:
    if challenge.pk is not None:
        challenge.refresh_from_db(fields=["metadata"])
    revision = get_challenge_stats_revision(challenge)
    cached = _read_cached_stats(challenge, revision)
    if cached is not None:
        return cached
    stats = compute_challenge_stats(challenge)
    _write_cached_stats(challenge, revision, stats)
    return stats


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

    has_group_stage = len(groups_preview) > 0
    round_bonus = 3 if has_group_stage else 1
    for stage in main_knockout_stages[1:]:
        for team_id in ub_hits.get(f"stage:{stage.id}", set()):
            scores[team_id] = scores.get(team_id, 0) + round_bonus
        if has_group_stage:
            round_bonus += 1

    if third_place_stage is not None:
        tp = ub.matchup_set.filter(stage=third_place_stage, position=1).first()
        if tp is not None and tp.winner_id is not None:
            winner_id = int(tp.winner_id)
            scores[winner_id] = scores.get(winner_id, 0) + 3

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


def compute_challenge_stats(challenge: BracketChallenge) -> dict[str, Any]:
    bracket = challenge.bracket
    groups_preview = bracket_groups_preview(bracket)

    user_brackets = list(
        UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            submitted_at__isnull=False,
        )
        .select_related("user")
        .prefetch_related("matchup_set__stage")
    )
    submitted_count = len(user_brackets)

    group_points_ctx = _build_group_points_context(bracket, user_brackets)

    group_stage: list[dict[str, Any]] = []
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
        max_points, avg_points, entries = _group_points_breakdown(
            group, user_brackets, group_points_ctx
        )
        group_stage.append(
            {
                "code": code,
                "teams": teams_out,
                "max_points": max_points,
                "avg_points": avg_points,
                "entries": entries,
            }
        )

    knockout_stages = list(
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT).order_by(
            "order"
        )
    )
    stage_columns = [
        {"key": f"stage:{stage.id}", "name": stage.name}
        for stage in reversed(knockout_stages)
    ]
    columns = [
        {"key": "progression_score", "name": "PROGRESSION SCORE"},
        {"key": "champion", "name": "Champions"},
        {"key": "runner_up", "name": "Runner-up"},
        *stage_columns,
        {"key": "group_winner", "name": "Group Winner"},
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

    knockout_rows: list[dict[str, Any]] = []
    contestants = (
        BracketContestant.objects.filter(bracket=bracket)
        .select_related("contestant")
        .prefetch_related("contestant__tags")
        .order_by("seed", "id")
    )
    for bc in contestants:
        pub = contestant_public(bc)
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
            }
        )

    return {
        "submitted_count": submitted_count,
        "group_stage": group_stage,
        "knockout": {"columns": columns, "rows": knockout_rows},
    }
