"""Validate and merge user bracket metadata (group picks, WC third-place list)."""

from __future__ import annotations

from typing import Any

from brackets.api.serializers import bracket_groups_preview
from brackets.utils.group_stage_config import (
    get_group_stage,
    group_stage_pick_requirements,
    is_qualifying_only_picking,
)


def _contestant_group_map(preview: list[dict[str, Any]]) -> dict[int, str]:
    out: dict[int, str] = {}
    for g in preview:
        code = g["code"]
        for t in g["teams"]:
            out[int(t["id"])] = code
    return out


def _ids_in_qualifying_slots(
    gp: dict[str, Any],
    *,
    qualifying: int,
) -> set[int]:
    ids: set[int] = set()
    for slots in gp.values():
        if not isinstance(slots, dict):
            continue
        for pos in range(1, qualifying + 1):
            cid = slots.get(str(pos))
            if cid is None:
                cid = slots.get(pos)
            if cid is None:
                continue
            try:
                ids.add(int(cid))
            except (TypeError, ValueError):
                pass
    return ids


def _third_ids_from_slot_three(gp: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    for slots in gp.values():
        if not isinstance(slots, dict):
            continue
        for key in ("3", 3):
            cid = slots.get(key)
            if cid is not None:
                try:
                    ids.add(int(cid))
                except (TypeError, ValueError):
                    pass
    return ids


def sanitize_group_metadata(bracket, meta: dict[str, Any]) -> dict[str, Any]:
    """
    Drop group picks for teams no longer in the bracket's groups.

    Stale ids can remain in stored metadata after roster changes; knockout sync
    uses the sanitized view via ``_placement_map``.
    """
    preview = bracket_groups_preview(bracket)
    if not preview:
        return meta

    meta = dict(meta)
    code_to_ids = {g["code"]: {t["id"] for t in g["teams"]} for g in preview}
    gp = meta.get("group_positions") or {}
    gs = get_group_stage(bracket)
    ranks_required = 0
    qualifying = 0
    qualifying_only = False
    if gs is not None:
        ranks_required, _ = group_stage_pick_requirements(gs)
        qualifying = gs.contestants_qualifying_per_group
        qualifying_only = is_qualifying_only_picking(gs)

    if not isinstance(gp, dict):
        meta["group_positions"] = {}
    else:
        cleaned: dict[str, dict[str, int | None]] = {}
        for code, slots in gp.items():
            if code not in code_to_ids or not isinstance(slots, dict):
                continue
            allowed = code_to_ids[code]
            row: dict[str, int | None] = {}
            for pos, cid in slots.items():
                try:
                    pos_i = int(pos)
                except (TypeError, ValueError):
                    continue
                if ranks_required > 0 and pos_i > ranks_required:
                    continue
                if cid is None:
                    row[str(pos_i)] = None
                    continue
                try:
                    ic = int(cid)
                except (TypeError, ValueError):
                    continue
                if ic in allowed:
                    row[str(pos_i)] = ic
            if row:
                cleaned[code] = row
        meta["group_positions"] = cleaned

    tp = meta.get("third_place_advancers") or []
    if isinstance(tp, list) and tp:
        gp_clean = meta.get("group_positions") or {}
        if qualifying_only and gs is not None:
            placed = _ids_in_qualifying_slots(gp_clean, qualifying=qualifying)
            all_ids = {t["id"] for g in preview for t in g["teams"]}
            allowed_tp = all_ids - placed
        else:
            allowed_tp = _third_ids_from_slot_three(gp_clean)
        meta["third_place_advancers"] = [
            int(x)
            for x in tp
            if x is not None and int(x) in allowed_tp
        ]

    return meta


def merge_and_validate_user_bracket_metadata(
    bracket,
    existing: dict[str, Any] | None,
    body: dict[str, Any],
) -> dict[str, Any]:
    meta = dict(existing) if isinstance(existing, dict) else {}
    if "group_positions" in body:
        gp = body["group_positions"]
        if gp is not None and not isinstance(gp, dict):
            raise ValueError("group_positions must be an object")
        meta["group_positions"] = gp if gp is not None else {}
    if "third_place_advancers" in body:
        tp = body["third_place_advancers"]
        if tp is not None and not isinstance(tp, list):
            raise ValueError("third_place_advancers must be a list")
        meta["third_place_advancers"] = tp if tp is not None else []
    meta = sanitize_group_metadata(bracket, meta)
    validate_group_metadata(bracket, meta)
    return meta


def validate_group_metadata(bracket, meta: dict[str, Any]) -> None:
    preview = bracket_groups_preview(bracket)
    if not preview:
        return

    code_to_ids = {g["code"]: {t["id"] for t in g["teams"]} for g in preview}
    gp = meta.get("group_positions") or {}
    gs = get_group_stage(bracket)
    ranks_required, third_count = (
        group_stage_pick_requirements(gs) if gs else (0, 0)
    )
    qualifying = gs.contestants_qualifying_per_group if gs else 0
    qualifying_only = bool(gs and is_qualifying_only_picking(gs))

    for code, slots in gp.items():
        if code not in code_to_ids:
            raise ValueError(f"Unknown group code: {code}")
        if not isinstance(slots, dict):
            raise ValueError("Each group_positions entry must be an object")
        allowed = code_to_ids[code]
        for pos, cid in slots.items():
            if cid is None:
                continue
            try:
                pos_i = int(pos)
            except (TypeError, ValueError):
                raise ValueError("Placement positions must be integers") from None
            if ranks_required > 0 and pos_i > ranks_required:
                raise ValueError(
                    f"Group {code} only uses positions 1–{ranks_required}"
                )
            try:
                ic = int(cid)
            except (TypeError, ValueError):
                raise ValueError("Placement ids must be integers") from None
            if ic not in allowed:
                raise ValueError(f"Contestant {ic} is not in group {code}")

    tp = meta.get("third_place_advancers") or []
    if not tp:
        return

    if third_count > 0 and len(tp) > third_count:
        raise ValueError(f"Choose at most {third_count} third-place teams")
    if third_count == 0 and tp:
        raise ValueError("This bracket does not use third-place advancers")

    seen: set[int] = set()
    for cid in tp:
        ic = int(cid)
        if ic in seen:
            raise ValueError("Duplicate team in third-place list")
        seen.add(ic)

    if qualifying_only:
        placed = _ids_in_qualifying_slots(gp, qualifying=qualifying)
        all_ids = {t["id"] for g in preview for t in g["teams"]}
        allowed_tp = all_ids - placed
        id_to_group = _contestant_group_map(preview)
        groups_seen: set[str] = set()
        for cid in tp:
            ic = int(cid)
            if ic not in allowed_tp:
                raise ValueError(
                    "Third-place advancers must be teams outside the "
                    "qualifying places in their group"
                )
            gcode = id_to_group.get(ic)
            if gcode is None:
                raise ValueError(f"Contestant {ic} is not in this bracket")
            if gcode in groups_seen:
                raise ValueError(
                    "At most one third-place advancer is allowed per group"
                )
            groups_seen.add(gcode)
        return

    third_assigned = _third_ids_from_slot_three(gp)
    for cid in tp:
        ic = int(cid)
        if ic not in third_assigned:
            raise ValueError(
                "Each third-place advancer must be placed 3rd in a group first"
            )
