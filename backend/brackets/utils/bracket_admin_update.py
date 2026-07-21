"""Apply admin PATCH payloads to brackets and stages."""

from __future__ import annotations

from typing import Any

from django.utils.dateparse import parse_datetime

from brackets.models import Bracket, BracketStage, GroupStage, KnockoutStage
from brackets.utils.bracket_structure_config import parse_bracket_metadata
from brackets.utils.group_stage_config import resolve_group_contestants_advancing


def _bool_val(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").lower() in ("true", "1", "on", "yes")


def apply_bracket_admin_fields(bracket: Bracket, body: dict[str, Any]) -> list[str]:
    """Mutate bracket from admin body; return ``update_fields``."""
    fields: list[str] = []

    if "randomize_seeds_per_challenge" in body:
        bracket.randomize_seeds_per_challenge = _bool_val(
            body["randomize_seeds_per_challenge"]
        )
        fields.append("randomize_seeds_per_challenge")

    if "show_seeds" in body:
        bracket.show_seeds = _bool_val(body["show_seeds"])
        fields.append("show_seeds")

    if "has_third_place_match" in body:
        bracket.has_third_place_match = _bool_val(body["has_third_place_match"])
        fields.append("has_third_place_match")

    for key in ("points_champion", "points_third_place_winner"):
        if key in body:
            n = int(body[key])
            if n < 0:
                raise ValueError(f"{key} must be 0 or greater")
            setattr(bracket, key, n)
            fields.append(key)

    if "metadata" in body:
        bracket.metadata = parse_bracket_metadata(body["metadata"])
        fields.append("metadata")

    return fields


def _parse_stage_metadata(raw: Any) -> Any:
    if raw is None:
        return None
    return parse_bracket_metadata(raw)


def apply_stage_admin_patch(stage: BracketStage, patch: dict[str, Any]) -> list[str]:
    """Mutate one stage; return base-model ``update_fields``."""
    fields: list[str] = []

    if "name" in patch:
        name = str(patch["name"] or "").strip()
        if not name:
            raise ValueError("stage name cannot be empty")
        stage.name = name
        fields.append("name")

    if "points_per_correct_pick" in patch:
        n = int(patch["points_per_correct_pick"])
        if n < 0:
            raise ValueError("points_per_correct_pick must be 0 or greater")
        stage.points_per_correct_pick = n
        fields.append("points_per_correct_pick")

    if "is_random_draw" in patch:
        stage.is_random_draw = _bool_val(patch["is_random_draw"])
        fields.append("is_random_draw")

    if "metadata" in patch:
        stage.metadata = _parse_stage_metadata(patch["metadata"])
        fields.append("metadata")

    if "submission_deadline" in patch:
        raw = patch["submission_deadline"]
        if raw is None or raw == "":
            stage.submission_deadline = None
        else:
            dt = parse_datetime(str(raw))
            if dt is None:
                raise ValueError("submission_deadline must be an ISO datetime")
            stage.submission_deadline = dt
        fields.append("submission_deadline")

    if stage.stage_type == BracketStage.StageType.GROUP:
        gs = GroupStage.objects.get(pk=stage.pk)
        gs_fields: list[str] = []

        for key in (
            "number_of_groups",
            "matches_per_contestant",
            "contestants_qualifying_per_group",
            "points_per_win",
            "points_per_tie",
            "points_per_loss",
            "points_per_exact_position",
            "points_per_advancer",
        ):
            if key in patch:
                n = int(patch[key])
                if n < 0:
                    raise ValueError(f"{key} must be 0 or greater")
                setattr(gs, key, n)
                gs_fields.append(key)

        if "ties_allowed" in patch:
            gs.ties_allowed = _bool_val(patch["ties_allowed"])
            gs_fields.append("ties_allowed")

        if "remaining_spots_strategy" in patch:
            raw = patch["remaining_spots_strategy"]
            gs.remaining_spots_strategy = (
                None if raw is None or raw == "" else str(raw)
            )
            gs_fields.append("remaining_spots_strategy")

        if "group_position_picking" in patch:
            raw = str(patch["group_position_picking"] or "").strip()
            valid = {
                c.value for c in GroupStage.GroupPositionPicking
            }
            if raw not in valid:
                raise ValueError(
                    "group_position_picking must be 'all' or 'qualifying_only'"
                )
            gs.group_position_picking = raw
            gs_fields.append("group_position_picking")

        if gs_fields:
            if (
                "contestants_qualifying_per_group" in gs_fields
                or "number_of_groups" in gs_fields
            ):
                stage.contestants_advancing = resolve_group_contestants_advancing(
                    gs, stage.bracket
                )
                fields.append("contestants_advancing")
            gs.save(update_fields=gs_fields)

    elif stage.stage_type == BracketStage.StageType.KNOCKOUT:
        ks = KnockoutStage.objects.get(pk=stage.pk)
        ks_fields: list[str] = []

        if "number_of_legs" in patch:
            n = int(patch["number_of_legs"])
            if n < 1:
                raise ValueError("number_of_legs must be at least 1")
            ks.number_of_legs = n
            ks_fields.append("number_of_legs")

        if "has_extra_time" in patch:
            ks.has_extra_time = _bool_val(patch["has_extra_time"])
            ks_fields.append("has_extra_time")

        if "has_penalty_shootout" in patch:
            ks.has_penalty_shootout = _bool_val(patch["has_penalty_shootout"])
            ks_fields.append("has_penalty_shootout")

        if "is_final" in patch:
            ks.is_final = _bool_val(patch["is_final"])
            ks_fields.append("is_final")

        if "combine_points_with_group_stage" in patch:
            ks.combine_points_with_group_stage = _bool_val(
                patch["combine_points_with_group_stage"]
            )
            ks_fields.append("combine_points_with_group_stage")

        if ks_fields:
            ks.save(update_fields=ks_fields)

    return fields
