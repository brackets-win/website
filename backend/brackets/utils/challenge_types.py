"""Bracket challenge instance types and behavior flags."""

from __future__ import annotations

CHALLENGE = "CHALLENGE"
TOURNAMENT = "TOURNAMENT"
POLL = "POLL"

ALL_BRACKET_INSTANCE_TYPES = frozenset({CHALLENGE, TOURNAMENT, POLL})


def creates_user_bracket(instance_type: str) -> bool:
    return instance_type in (CHALLENGE, POLL)


def uses_prediction_scoring(instance_type: str) -> bool:
    return instance_type == CHALLENGE


def uses_bracket_submission(instance_type: str) -> bool:
    return instance_type == CHALLENGE


def master_bracket_is_results_source(instance_type: str) -> bool:
    return instance_type in (CHALLENGE, TOURNAMENT)
