"""Bracket metadata flag for the admin-designated "next match".

The next match is a single, currently-undecided knockout matchup on the master
bracket. When set, the challenge leaderboard shows a "Next Match" column with the
contestant each player wants to win that game.
"""

from __future__ import annotations

from typing import Any

NEXT_MATCH_KEY = "next_match_matchup_id"


def get_next_match_matchup_id(metadata: Any) -> int | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get(NEXT_MATCH_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def set_next_match_on_metadata(metadata: Any, matchup_id: int | None) -> dict[str, Any]:
    base = dict(metadata) if isinstance(metadata, dict) else {}
    if matchup_id is None:
        base.pop(NEXT_MATCH_KEY, None)
    else:
        base[NEXT_MATCH_KEY] = int(matchup_id)
    return base


def get_next_match_matchup(bracket):
    """Return the valid master next-match ``Matchup``, or ``None``.

    Valid means it points at a knockout matchup on this bracket's master that has
    both contestants set and no winner yet (an actual upcoming game).
    """
    from brackets.models import BracketStage, Matchup, UserBracket

    matchup_id = get_next_match_matchup_id(bracket.metadata)
    if matchup_id is None:
        return None
    master = UserBracket.objects.filter(bracket=bracket, is_master=True).first()
    if master is None:
        return None
    m = (
        Matchup.objects.filter(pk=matchup_id, user_bracket=master)
        .select_related(
            "stage",
            "contestant1__contestant",
            "contestant2__contestant",
        )
        .first()
    )
    if m is None:
        return None
    if m.stage.stage_type != BracketStage.StageType.KNOCKOUT:
        return None
    if m.contestant1_id is None or m.contestant2_id is None:
        return None
    if m.winner_id is not None:
        return None
    return m


def show_next_match_for_bracket(bracket) -> bool:
    """True when a valid next match is set and projections aren't hidden."""
    from brackets.utils.group_results_mode import (
        omit_leaderboard_potential_for_bracket,
    )

    if omit_leaderboard_potential_for_bracket(bracket):
        return False
    return get_next_match_matchup(bracket) is not None
