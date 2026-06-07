"""Aggregate pick statistics for a bracket challenge."""

from __future__ import annotations

from typing import Any

from brackets.api.serializers import bracket_groups_preview, contestant_public
from brackets.models import BracketChallenge, BracketContestant, BracketStage, KnockoutStage, UserBracket
from brackets.utils.sync_group_knockout import contestants_in_stage_for_scoring


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


def compute_challenge_stats(challenge: BracketChallenge) -> dict[str, Any]:
    bracket = challenge.bracket
    groups_preview = bracket_groups_preview(bracket)

    user_brackets = list(
        UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            submitted_at__isnull=False,
        ).prefetch_related("matchup_set__stage")
    )
    submitted_count = len(user_brackets)

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
        group_stage.append({"code": code, "teams": teams_out})

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
    contestants = BracketContestant.objects.filter(bracket=bracket).select_related(
        "contestant"
    ).order_by("seed", "id")
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
