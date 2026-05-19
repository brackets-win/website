"""Wire WC 2026 knockout matchups from FIFA regulation feeder table (non-standard tree)."""

from __future__ import annotations

import re

from django.db import transaction

from brackets.data.fwc26.r32_tree_slots import R32_TREE_SLOTS
from brackets.models import BracketStage, Matchup, UserBracket
from brackets.utils.fwc26_regulations import load_knockout_matchups_raw, parse_knockout_matchups_tsv

# R32 match code → tree position (1–16) on first knockout stage.
R32_MATCH_TO_TREE_POS: dict[str, int] = {
    "M74": 1,
    "M77": 2,
    "M73": 3,
    "M75": 4,
    "M76": 5,
    "M78": 6,
    "M79": 7,
    "M80": 8,
    "M81": 9,
    "M82": 10,
    "M83": 11,
    "M84": 12,
    "M85": 13,
    "M86": 14,
    "M87": 15,
    "M88": 16,
}

_ROUND_ORDER = (
    "Round of 32",
    "Round of 16",
    "Quarter Final",
    "Semi Final",
)

_FEEDER_NUM_RE = re.compile(r"\((\d+)\)")
_WINNER_NUM_RE = re.compile(r"Winner\s*\((\d+)\)")


def _is_wc_bracket(bracket) -> bool:
    meta = bracket.metadata or {}
    return meta.get("tournament_type") == "world_cup_2026"


def _feeder_winner_num(text: str) -> int | None:
    m = _FEEDER_NUM_RE.search(text or "")
    return int(m.group(1)) if m else None


def _slot_winner_num(winner_slot: str) -> int | None:
    m = _WINNER_NUM_RE.search(winner_slot or "")
    return int(m.group(1)) if m else None


def _ko_stages_by_round(bracket) -> dict[str, BracketStage]:
    from brackets.models import KnockoutStage

    ko = list(
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT).order_by(
            "order"
        )
    )
    main: list[BracketStage] = []
    for stage in ko:
        ks = KnockoutStage.objects.filter(pk=stage.pk).first()
        if ks and (ks.is_third_place or ks.is_final):
            continue
        main.append(stage)

    return {
        label: stage for label, stage in zip(_ROUND_ORDER, main, strict=False)
    }


@transaction.atomic
def wire_fwc26_knockout_sources(user_bracket: UserBracket) -> int:
    """
    Set ``source_*_matchup`` on WC knockout rows from ``knockout_matchups.tsv``.

    Returns count of matchups updated.
    """
    bracket = user_bracket.bracket
    if not _is_wc_bracket(bracket):
        return 0

    rows = parse_knockout_matchups_tsv(load_knockout_matchups_raw())
    stages = _ko_stages_by_round(bracket)
    if "Round of 32" not in stages:
        return 0

    r32 = stages["Round of 32"]
    winners: dict[int, Matchup] = {}
    updated = 0
    round_counters: dict[str, int] = {}

    for row in rows:
        rnd = row["round"]
        match_no = row["match_no"]
        winner_num = _slot_winner_num(row.get("winner_slot", ""))

        if rnd == "Round of 32":
            tree_pos = R32_MATCH_TO_TREE_POS.get(match_no)
            if tree_pos is None:
                continue
            try:
                m = Matchup.objects.get(
                    user_bracket=user_bracket, stage=r32, position=tree_pos
                )
            except Matchup.DoesNotExist:
                continue
            if winner_num is not None:
                winners[winner_num] = m
            continue

        stage = stages.get(rnd)
        if stage is None or winner_num is None:
            continue

        round_counters[rnd] = round_counters.get(rnd, 0) + 1
        position = round_counters[rnd]

        try:
            m = Matchup.objects.get(
                user_bracket=user_bracket, stage=stage, position=position
            )
        except Matchup.DoesNotExist:
            continue

        feed_a = _feeder_winner_num(row["team_a"])
        feed_b = _feeder_winner_num(row["team_b"])
        src_a = winners.get(feed_a) if feed_a else None
        src_b = winners.get(feed_b) if feed_b else None

        changed_fields: list[str] = []
        if src_a and m.source_a_matchup_id != src_a.pk:
            m.source_a_matchup = src_a
            m.source_a_uses_winner = True
            changed_fields.extend(["source_a_matchup", "source_a_uses_winner"])
        if src_b and m.source_b_matchup_id != src_b.pk:
            m.source_b_matchup = src_b
            m.source_b_uses_winner = True
            changed_fields.extend(["source_b_matchup", "source_b_uses_winner"])

        if changed_fields:
            m.save(update_fields=changed_fields)
            updated += 1

        winners[winner_num] = m

    return updated
