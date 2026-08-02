"""Batch-loaded data for challenge list/summary API responses."""

from __future__ import annotations

from typing import Any

from brackets.models import Bracket, BracketChallenge, UserBracket
from brackets.utils.challenge_outcomes import show_outcomes_tab_for_challenge
from brackets.utils.challenge_types import CHALLENGE
from brackets.utils.leaderboard_preview import (
    _EMPTY_PREVIEW,
    bracket_challenge_leaderboard_previews,
)
from brackets.utils.leaderboard_scoring import (
    LeaderboardScoringContext,
    load_leaderboard_scoring_context,
)


def master_user_bracket_ids_for_brackets(
    bracket_ids: set[int],
) -> dict[int, int]:
    if not bracket_ids:
        return {}
    return {
        row["bracket_id"]: row["id"]
        for row in UserBracket.objects.filter(
            bracket_id__in=bracket_ids,
            is_master=True,
        ).values("id", "bracket_id")
    }


def user_brackets_by_challenge(
    user,
    challenge_ids: set[int],
) -> dict[int, list[UserBracket]]:
    by_challenge: dict[int, list[UserBracket]] = {}
    if not challenge_ids:
        return by_challenge
    for ub in UserBracket.objects.filter(
        user=user,
        is_master=False,
        challenge_id__in=challenge_ids,
    ).order_by("-created_at"):
        by_challenge.setdefault(ub.challenge_id, []).append(ub)
    return by_challenge


def scoring_contexts_for_brackets(
    brackets_by_id: dict[int, Bracket],
) -> dict[int, LeaderboardScoringContext]:
    return {
        bracket_id: load_leaderboard_scoring_context(bracket)
        for bracket_id, bracket in brackets_by_id.items()
    }


class ChallengeSummaryBootstrap:
    """One query batch per expensive summary field across many challenges."""

    __slots__ = ("_master_ids", "_outcomes_tabs", "_previews", "_tournament_finals")

    def __init__(self, challenges: list[BracketChallenge], user=None) -> None:
        from brackets.utils.tournament_final_summary import load_tournament_finals

        bracket_ids = {c.bracket_id for c in challenges}
        self._master_ids = master_user_bracket_ids_for_brackets(bracket_ids)
        brackets_by_id = {c.bracket_id: c.bracket for c in challenges}
        scoring_contexts = scoring_contexts_for_brackets(brackets_by_id)
        self._previews = bracket_challenge_leaderboard_previews(challenges, user)
        self._tournament_finals = load_tournament_finals(challenges)
        self._outcomes_tabs: dict[int, bool] = {}
        for challenge in challenges:
            if challenge.instance_type != CHALLENGE:
                self._outcomes_tabs[challenge.id] = False
            else:
                ctx = scoring_contexts.get(challenge.bracket_id)
                self._outcomes_tabs[challenge.id] = show_outcomes_tab_for_challenge(
                    challenge,
                    scoring_ctx=ctx,
                )

    def master_user_bracket_id(
        self,
        challenge: BracketChallenge,
        *,
        is_participant: bool,
    ) -> int | None:
        if not is_participant:
            return None
        return self._master_ids.get(challenge.bracket_id)

    def leaderboard_preview(self, challenge: BracketChallenge) -> dict[str, Any]:
        return self._previews.get(challenge.id, dict(_EMPTY_PREVIEW))

    def show_outcomes_tab(self, challenge: BracketChallenge) -> bool:
        return self._outcomes_tabs.get(challenge.id, False)

    def tournament_final(
        self, challenge: BracketChallenge
    ) -> dict[str, Any] | None:
        return self._tournament_finals.get(challenge.id)
