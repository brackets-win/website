"""Fill first knockout round from user group-stage picks (metadata)."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from brackets.api.serializers import bracket_groups_preview
from brackets.models import BracketContestant, BracketStage, Matchup, UserBracket
from brackets.utils.fwc26_regulations import teams_to_bit_vector
from brackets.utils.group_knockout_mapping import generate_default_group_knockout_mapping
from brackets.utils.knockout_rebuild import rebuild_knockout_from_first_round
from brackets.utils.knockout_tree import ensure_knockout_matchup_shell


def parse_position_code(code: str) -> tuple[str, int] | None:
    """
    Parse a group finish code into (group_letter, position).

    Supports ``A1``, ``1A``, and ``3A`` (third in group A).
    """
    code = (code or "").strip().upper()
    if len(code) < 2:
        return None
    if code[0] == "3" and code[1].isalpha():
        return code[1], 3
    if code[0].isalpha() and code[1:].isdigit():
        return code[0], int(code[1:])
    if code[0].isdigit() and code[1].isalpha():
        return code[1], int(code[0])
    return None


def to_first_place_slot_code(code: str) -> str | None:
    """Normalize winner codes to ``1A`` style for WC third-place lookup keys."""
    parsed = parse_position_code(code)
    if parsed is None:
        return None
    group, pos = parsed
    if pos == 1:
        return f"1{group}"
    return None


def _get_first_knockout_stage(bracket):
    return (
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT)
        .order_by("order")
        .first()
    )


def _load_knockout_mapping(bracket, knockout_stage) -> list[tuple[int, str, str]]:
    if knockout_stage.metadata and "group_knockout_mapping" in knockout_stage.metadata:
        mapping_data = knockout_stage.metadata["group_knockout_mapping"]
        out: list[tuple[int, str, str]] = []
        for pos_str, teams in mapping_data.items():
            out.append((int(pos_str), teams["team_a"], teams["team_b"]))
        return sorted(out, key=lambda x: x[0])

    group_stage = (
        bracket.stages.filter(stage_type=BracketStage.StageType.GROUP)
        .order_by("order")
        .first()
    )
    if group_stage is None:
        return []
    from brackets.models import GroupStage

    gs = GroupStage.objects.get(pk=group_stage.pk)
    return generate_default_group_knockout_mapping(gs.number_of_groups)


def _placement_map(
    bracket,
    metadata: dict[str, Any],
) -> dict[str, dict[int, int]]:
    """group code -> {finish position: bracket_contestant_id}."""
    preview = bracket_groups_preview(bracket)
    if not preview:
        return {}

    gp = metadata.get("group_positions") or {}
    out: dict[str, dict[int, int]] = {}
    for g in preview:
        code = g["code"]
        allowed = {t["id"] for t in g["teams"]}
        slots = gp.get(code) or {}
        if not isinstance(slots, dict):
            continue
        row: dict[int, int] = {}
        for key, cid in slots.items():
            if cid is None:
                continue
            try:
                pos = int(key)
                ic = int(cid)
            except (TypeError, ValueError):
                continue
            if ic in allowed:
                row[pos] = ic
        if row:
            out[code] = row
    return out


def _third_place_group_codes(
    metadata: dict[str, Any],
    placements: dict[str, dict[int, int]],
) -> list[str]:
    """Which groups contribute a third-place advancer (``3A`` … ``3L``)."""
    advancers = metadata.get("third_place_advancers") or []
    if not advancers:
        return []

    codes: list[str] = []
    adv_set = {int(x) for x in advancers}
    for group_code, row in placements.items():
        third_id = row.get(3)
        if third_id is not None and third_id in adv_set:
            codes.append(f"3{group_code}")
    return codes


def _wc_third_place_pairings(
    bracket,
    third_place_codes: list[str],
) -> dict[str, str] | None:
    """
  Map first-place slots (``1A``) to third-place group codes (``3C``) per FIFA table.
    """
    meta = bracket.metadata or {}
    combinations = meta.get("third_place_combinations")
    if not combinations or len(third_place_codes) < 8:
        return None
    bit_vector = teams_to_bit_vector(third_place_codes)
    combo = combinations.get(str(bit_vector))
    if not combo:
        return None
    matchups = combo.get("matchups")
    if not isinstance(matchups, dict):
        return None
    return matchups


def _resolve_position_code(
    code: str,
    *,
    placements: dict[str, dict[int, int]],
    wc_pairings: dict[str, str] | None,
    partner_code: str | None,
    is_wc: bool = False,
) -> int | None:
    """
    Resolve a mapping code to a ``BracketContestant`` id.

    For World Cup, 1st/2nd (``A1``, ``A2``, …) fill as soon as the user sets group
    order. Third-place knockout slots (``3X`` in the R32 template) stay empty until
    all 8 third-place advancers are chosen; then FIFA combination lookup assigns them.
    """
    parsed = parse_position_code(code)
    if parsed is None:
        return None
    group, pos = parsed

    if pos == 3 and is_wc:
        if wc_pairings is None or not partner_code:
            return None
        winner_slot = to_first_place_slot_code(partner_code)
        if not winner_slot or winner_slot not in wc_pairings:
            return None
        actual = wc_pairings[winner_slot]
        actual_parsed = parse_position_code(actual)
        if not actual_parsed:
            return None
        group, pos = actual_parsed

    row = placements.get(group)
    if not row:
        return None
    return row.get(pos)


@transaction.atomic
def sync_first_knockout_from_group_picks(user_bracket: UserBracket) -> int:
    """
    Update first knockout round contestants from ``group_positions`` metadata.

    Returns the number of first-round matchups updated.
    """
    bracket = user_bracket.bracket
    if not bracket.stages.filter(stage_type=BracketStage.StageType.GROUP).exists():
        return 0

    first_ko = _get_first_knockout_stage(bracket)
    if first_ko is None:
        return 0

    ensure_knockout_matchup_shell(user_bracket)

    metadata = user_bracket.metadata if isinstance(user_bracket.metadata, dict) else {}
    placements = _placement_map(bracket, metadata)
    if not placements:
        return 0

    mapping = _load_knockout_mapping(bracket, first_ko)
    if not mapping:
        return 0

    is_wc = (bracket.metadata or {}).get("tournament_type") == "world_cup_2026"
    wc_pairings: dict[str, str] | None = None
    if is_wc:
        third_codes = _third_place_group_codes(metadata, placements)
        wc_pairings = _wc_third_place_pairings(bracket, third_codes)

    updated = 0
    for position, team_a_code, team_b_code in mapping:
        try:
            m = Matchup.objects.get(
                user_bracket=user_bracket,
                stage=first_ko,
                position=position,
            )
        except Matchup.DoesNotExist:
            continue

        bc_a_id = _resolve_position_code(
            team_a_code,
            placements=placements,
            wc_pairings=wc_pairings,
            partner_code=team_b_code,
            is_wc=is_wc,
        )
        bc_b_id = _resolve_position_code(
            team_b_code,
            placements=placements,
            wc_pairings=wc_pairings,
            partner_code=team_a_code,
            is_wc=is_wc,
        )

        bc_a = (
            BracketContestant.objects.filter(pk=bc_a_id).first()
            if bc_a_id
            else None
        )
        bc_b = (
            BracketContestant.objects.filter(pk=bc_b_id).first()
            if bc_b_id
            else None
        )

        changed = (
            m.contestant1_id != (bc_a.id if bc_a else None)
            or m.contestant2_id != (bc_b.id if bc_b else None)
        )
        if not changed:
            continue

        m.contestant1 = bc_a
        m.contestant2 = bc_b
        m.winner = None
        m.save(update_fields=["contestant1", "contestant2", "winner"])
        updated += 1

    if updated:
        rebuild_knockout_from_first_round(user_bracket)

    return updated
