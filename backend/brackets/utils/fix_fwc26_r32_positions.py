"""Reposition existing WC 2026 R32 matchups to bracket tree order from r32_tree_slots."""

from __future__ import annotations

from django.db import transaction

from brackets.data.fwc26.r32_tree_slots import (
    R32_TREE_SLOTS,
    build_r32_group_knockout_mapping,
)
from brackets.models import Bracket, BracketStage, Matchup, UserBracket
from brackets.utils.group_knockout_fill import MAPPING, apply_knockout_fill_to_stage
from brackets.utils.knockout_rebuild import rebuild_knockout_from_first_round
from brackets.utils.sync_group_knockout import sync_first_knockout_from_group_picks

# FIFA regulations table row order (first seed), for brackets never migrated.
_LEGACY_R32_SLOTS: tuple[tuple[int, str, str], ...] = (
    (1, "A2", "B2"),
    (2, "E1", "3E"),
    (3, "F1", "C2"),
    (4, "C1", "F2"),
    (5, "I1", "3I"),
    (6, "E2", "I2"),
    (7, "A1", "3A"),
    (8, "L1", "3L"),
    (9, "D1", "3D"),
    (10, "G1", "3G"),
    (11, "K2", "L2"),
    (12, "H1", "J2"),
    (13, "B1", "3B"),
    (14, "J1", "H2"),
    (15, "K1", "3K"),
    (16, "D2", "G2"),
)

_TARGET_BY_PAIR = {(a, b): pos for pos, a, b in R32_TREE_SLOTS}
_EXPECTED_AT_POS = {pos: (a, b) for pos, a, b in R32_TREE_SLOTS}


def _first_knockout_stage(bracket: Bracket) -> BracketStage | None:
    return (
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT)
        .order_by("order")
        .first()
    )


def _pair_at_position(
    position: int,
    mapping_data: dict,
    legacy_by_pos: dict[int, tuple[str, str]],
) -> tuple[str, str] | None:
    entry = mapping_data.get(str(position))
    if entry and entry.get("team_a") and entry.get("team_b"):
        return entry["team_a"], entry["team_b"]
    return legacy_by_pos.get(position)


def _needs_r32_reposition(
    matchups: list[Matchup],
    mapping_data: dict,
    legacy_by_pos: dict[int, tuple[str, str]],
) -> bool:
    current_pos: dict[tuple[str, str], int] = {}
    for m in matchups:
        pair = _pair_at_position(m.position, mapping_data, legacy_by_pos)
        if pair:
            current_pos[pair] = m.position
    for pair, target_pos in _TARGET_BY_PAIR.items():
        if current_pos.get(pair) != target_pos:
            return True
    return False


@transaction.atomic
def fix_fwc26_r32_tree_positions(bracket: Bracket) -> int:
    """
    Move R32 matchups to tree positions from ``r32_tree_slots`` for every user bracket.

    Returns the number of user brackets updated (0 if already correct or not WC).
    """
    if (bracket.metadata or {}).get("tournament_type") != "world_cup_2026":
        return 0

    first_ko = _first_knockout_stage(bracket)
    if first_ko is None:
        return 0

    mapping_data = (first_ko.metadata or {}).get("group_knockout_mapping") or {}
    legacy_by_pos = {pos: (a, b) for pos, a, b in _LEGACY_R32_SLOTS}
    updated_brackets = 0

    for ub in UserBracket.objects.filter(bracket=bracket):
        matchups = list(
            Matchup.objects.filter(user_bracket=ub, stage=first_ko).order_by("position")
        )
        if len(matchups) != len(R32_TREE_SLOTS):
            continue
        if not _needs_r32_reposition(matchups, mapping_data, legacy_by_pos):
            continue

        matchup_by_pair: dict[tuple[str, str], Matchup] = {}
        for m in matchups:
            pair = _pair_at_position(m.position, mapping_data, legacy_by_pos)
            if pair:
                matchup_by_pair[pair] = m

        target: dict[int, int] = {}
        missing = False
        for pair, target_pos in _TARGET_BY_PAIR.items():
            m = matchup_by_pair.get(pair)
            if m is None:
                missing = True
                break
            target[m.id] = target_pos
        if missing:
            continue

        offset = 10_000
        for m in matchups:
            m.position = offset + m.position
            m.save(update_fields=["position"])
        for m in matchups:
            m.position = target[m.id]
            m.save(update_fields=["position"])

        Matchup.objects.filter(
            user_bracket=ub,
            stage__order__gt=first_ko.order,
        ).update(contestant1=None, contestant2=None, winner=None)

        sync_first_knockout_from_group_picks(ub, ensure_shell=False)
        rebuild_knockout_from_first_round(ub)
        updated_brackets += 1

    apply_knockout_fill_to_stage(
        first_ko,
        build_r32_group_knockout_mapping(),
        method=MAPPING,
    )

    return updated_brackets
