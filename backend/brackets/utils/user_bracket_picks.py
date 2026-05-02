"""Validate and merge user bracket metadata (group picks, WC third-place list)."""

from __future__ import annotations

from typing import Any

from brackets.api.serializers import bracket_groups_preview


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
    validate_group_metadata(bracket, meta)
    return meta


def validate_group_metadata(bracket, meta: dict[str, Any]) -> None:
    preview = bracket_groups_preview(bracket)
    if not preview:
        return

    code_to_ids = {g["code"]: {t["id"] for t in g["teams"]} for g in preview}
    gp = meta.get("group_positions") or {}

    for code, slots in gp.items():
        if code not in code_to_ids:
            raise ValueError(f"Unknown group code: {code}")
        if not isinstance(slots, dict):
            raise ValueError("Each group_positions entry must be an object")
        allowed = code_to_ids[code]
        for _pos, cid in slots.items():
            if cid is None:
                continue
            try:
                ic = int(cid)
            except (TypeError, ValueError):
                raise ValueError("Placement ids must be integers") from None
            if ic not in allowed:
                raise ValueError(f"Contestant {ic} is not in group {code}")

    tp = meta.get("third_place_advancers") or []
    if not tp:
        return

    meta_wc = (bracket.metadata or {}).get("tournament_type") == "world_cup_2026"
    if meta_wc and len(tp) > 8:
        raise ValueError("Choose at most 8 third-place teams")

    seen: set[int] = set()
    for cid in tp:
        ic = int(cid)
        if ic in seen:
            raise ValueError("Duplicate team in third-place list")
        seen.add(ic)

    third_assigned: set[int] = set()
    for slots in gp.values():
        if not isinstance(slots, dict):
            continue
        t = slots.get("3")
        if t is None:
            t = slots.get(3)
        if t is not None:
            third_assigned.add(int(t))

    for cid in tp:
        ic = int(cid)
        if ic not in third_assigned:
            raise ValueError(
                "Each third-place advancer must be placed 3rd in a group first"
            )
