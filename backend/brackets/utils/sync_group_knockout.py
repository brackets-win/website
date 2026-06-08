"""Fill first knockout round from user group-stage picks (metadata)."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from brackets.api.serializers import bracket_groups_preview
from brackets.models import BracketContestant, BracketStage, Matchup, UserBracket
from brackets.utils.fwc26_regulations import teams_to_bit_vector
from brackets.utils.group_knockout_fill import (
    ensure_knockout_fill_method_persisted,
    load_knockout_mapping,
    uses_wc_third_place_table,
)
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


def projected_first_knockout_contestant_ids(user_bracket: UserBracket) -> set[int]:
    """
    Bracket contestant ids that would occupy the first knockout round from
    ``group_positions`` metadata (without reading or writing matchups).
    """
    bracket = user_bracket.bracket
    if not bracket.stages.filter(stage_type=BracketStage.StageType.GROUP).exists():
        return set()

    first_ko = _get_first_knockout_stage(bracket)
    if first_ko is None:
        return set()

    metadata = user_bracket.metadata if isinstance(user_bracket.metadata, dict) else {}
    placements = _placement_map(bracket, metadata)
    if not placements:
        return set()

    mapping = load_knockout_mapping(bracket, first_ko)
    if not mapping:
        return set()

    is_wc = uses_wc_third_place_table(bracket, first_ko)
    wc_pairings: dict[str, str] | None = None
    if is_wc:
        third_codes = _third_place_group_codes(metadata, placements)
        wc_pairings = _wc_third_place_pairings(bracket, third_codes)

    ids: set[int] = set()
    for _position, team_a_code, team_b_code in mapping:
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
        if bc_a_id is not None:
            ids.add(bc_a_id)
        if bc_b_id is not None:
            ids.add(bc_b_id)
    return ids


def contestants_in_stage_for_scoring(user_bracket: UserBracket, stage) -> set[int]:
    """Teams in a knockout stage (matchups + projected R32 from group picks)."""
    ids = set(user_bracket.get_contestants_in_stage(stage))
    first_ko = _get_first_knockout_stage(user_bracket.bracket)
    if first_ko is not None and stage.pk == first_ko.pk:
        ids |= projected_first_knockout_contestant_ids(user_bracket)
    return ids


def contestants_credited_for_knockout_score(
    user_bracket: UserBracket, stage
) -> set[int]:
    """
    Teams that earn knockout stage points vs the master bracket.

    For group → knockout, the first round follows ``group_positions`` metadata
    only — not stale ``Matchup`` rows left after a team is removed from groups.
    """
    bracket = user_bracket.bracket
    has_group = bracket.stages.filter(
        stage_type=BracketStage.StageType.GROUP
    ).exists()
    first_ko = _get_first_knockout_stage(bracket)
    if first_ko is not None and stage.pk == first_ko.pk:
        if has_group:
            return projected_first_knockout_contestant_ids(user_bracket)
        return set()
    return set(user_bracket.get_contestants_in_stage(stage))


@transaction.atomic
def sync_first_knockout_from_group_picks(
    user_bracket: UserBracket,
    *,
    ensure_shell: bool = True,
) -> int:
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

    if ensure_shell:
        ensure_knockout_matchup_shell(user_bracket)

    ensure_knockout_fill_method_persisted(first_ko, bracket)

    metadata = user_bracket.metadata if isinstance(user_bracket.metadata, dict) else {}
    placements = _placement_map(bracket, metadata)

    mapping = load_knockout_mapping(bracket, first_ko)
    if not mapping:
        return 0

    is_wc = uses_wc_third_place_table(bracket, first_ko)
    wc_pairings: dict[str, str] | None = None
    if is_wc and placements:
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

        bc_a_id = (
            _resolve_position_code(
                team_a_code,
                placements=placements,
                wc_pairings=wc_pairings,
                partner_code=team_b_code,
                is_wc=is_wc,
            )
            if placements
            else None
        )
        bc_b_id = (
            _resolve_position_code(
                team_b_code,
                placements=placements,
                wc_pairings=wc_pairings,
                partner_code=team_a_code,
                is_wc=is_wc,
            )
            if placements
            else None
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

        next_c1 = bc_a.id if bc_a else None
        next_c2 = bc_b.id if bc_b else None
        changed = m.contestant1_id != next_c1 or m.contestant2_id != next_c2
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


def resync_group_knockout_for_bracket(bracket) -> None:
    """Sanitize group metadata and re-fill first knockout for every user bracket."""
    from brackets.models import UserBracket
    from brackets.utils.user_bracket_picks import sanitize_group_metadata

    for ub in UserBracket.objects.filter(bracket=bracket):
        raw = ub.metadata if isinstance(ub.metadata, dict) else {}
        cleaned = sanitize_group_metadata(bracket, raw)
        if cleaned != raw:
            ub.metadata = cleaned
            ub.save(update_fields=["metadata"])
        sync_first_knockout_from_group_picks(ub)
