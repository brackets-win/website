"""Compact final-matchup payload for tournament cards on the home list."""

from __future__ import annotations

from typing import Any

from brackets.models import BracketChallenge, KnockoutStage, Matchup, UserBracket
from brackets.utils.challenge_types import TOURNAMENT
from brackets.utils.matchup_scores import parse_stored_legs, scores_public
from brackets.utils.results_entry import KO_SCORE, results_entry_from_bracket


def serialize_tournament_final(
    matchup: Matchup,
    *,
    knockout_entry: str,
) -> dict[str, Any] | None:
    """Return a public final summary when the champion is decided."""
    from brackets.api.serializers import contestant_public

    if matchup.winner_id is None:
        return None
    if matchup.contestant1_id is None or matchup.contestant2_id is None:
        return None

    scores_out = None
    if knockout_entry == KO_SCORE:
        legs = parse_stored_legs(matchup.scores)
        if legs:
            scores_out = scores_public(legs)

    return {
        "knockout_entry": knockout_entry,
        "contestant1": contestant_public(matchup.contestant1),
        "contestant2": contestant_public(matchup.contestant2),
        "winner_id": matchup.winner_id,
        "scores": scores_out,
    }


def load_tournament_finals(
    challenges: list[BracketChallenge],
) -> dict[int, dict[str, Any]]:
    """
    Map challenge id → final summary for completed tournament finals.

    Batched for the home challenge list (no N+1 per card).
    """
    tournaments = [c for c in challenges if c.instance_type == TOURNAMENT]
    if not tournaments:
        return {}

    bracket_ids = {c.bracket_id for c in tournaments}
    masters = {
        ub.bracket_id: ub
        for ub in UserBracket.objects.filter(
            bracket_id__in=bracket_ids,
            is_master=True,
        ).only("id", "bracket_id")
    }
    final_stages = {
        ks.bracket_id: ks
        for ks in KnockoutStage.objects.filter(
            bracket_id__in=bracket_ids,
            is_final=True,
        ).only("id", "bracket_id")
    }

    lookups: list[tuple[BracketChallenge, int, int]] = []
    for challenge in tournaments:
        master = masters.get(challenge.bracket_id)
        stage = final_stages.get(challenge.bracket_id)
        if master is None or stage is None:
            continue
        lookups.append((challenge, master.id, stage.id))
    if not lookups:
        return {}

    matchups = (
        Matchup.objects.filter(
            user_bracket_id__in={ub_id for _, ub_id, _ in lookups},
            stage_id__in={stage_id for _, _, stage_id in lookups},
            winner_id__isnull=False,
        )
        .select_related(
            "contestant1__contestant",
            "contestant2__contestant",
            "winner__contestant",
        )
        .prefetch_related(
            "contestant1__contestant__tags",
            "contestant2__contestant__tags",
            "winner__contestant__tags",
        )
    )
    by_key = {(m.user_bracket_id, m.stage_id): m for m in matchups}

    out: dict[int, dict[str, Any]] = {}
    for challenge, ub_id, stage_id in lookups:
        matchup = by_key.get((ub_id, stage_id))
        if matchup is None:
            continue
        knockout_entry = results_entry_from_bracket(challenge.bracket)["knockout"]
        payload = serialize_tournament_final(
            matchup,
            knockout_entry=knockout_entry,
        )
        if payload is not None:
            out[challenge.id] = payload
    return out
