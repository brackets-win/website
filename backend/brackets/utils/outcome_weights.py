"""Manual rankings and matchup odds for weighted challenge outcomes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from brackets.models import Bracket, BracketStage, UserBracket
from brackets.utils.leaderboard_scoring import LeaderboardScoringContext
from brackets.utils.potential_knockout import MemMatchup, TreeState

OUTCOME_WEIGHTS_KEY = "outcome_weights"
TEAM_RANKINGS_KEY = "team_rankings"
MATCHUP_ODDS_KEY = "matchup_odds"

# How much stored matchup odds nudge FIFA-based ratings for later rounds.
CALIBRATION_RATING_NUDGE = 200.0


@dataclass(frozen=True)
class OutcomeWeights:
    """Admin-configured strength data for likelihood on the outcomes tab."""

    team_rankings: dict[int, int]
    matchup_win_pct: dict[int, float]


def _empty_weights() -> OutcomeWeights:
    return OutcomeWeights(team_rankings={}, matchup_win_pct={})


def parse_positive_rank(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return parsed


def parse_win_pct(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0 or parsed > 100:
        return None
    return round(parsed, 1)


def get_outcome_weights(bracket: Bracket) -> OutcomeWeights:
    meta = bracket.metadata if isinstance(bracket.metadata, dict) else {}
    raw = meta.get(OUTCOME_WEIGHTS_KEY)
    if not isinstance(raw, dict):
        return _empty_weights()

    team_rankings: dict[int, int] = {}
    raw_rankings = raw.get(TEAM_RANKINGS_KEY)
    if isinstance(raw_rankings, dict):
        for key, value in raw_rankings.items():
            try:
                team_id = int(key)
            except (TypeError, ValueError):
                continue
            rank = parse_positive_rank(value)
            if rank is not None:
                team_rankings[team_id] = rank

    matchup_win_pct: dict[int, float] = {}
    raw_odds = raw.get(MATCHUP_ODDS_KEY)
    if isinstance(raw_odds, dict):
        for key, value in raw_odds.items():
            try:
                matchup_id = int(key)
            except (TypeError, ValueError):
                continue
            pct = parse_win_pct(value)
            if pct is not None:
                matchup_win_pct[matchup_id] = pct

    return OutcomeWeights(
        team_rankings=team_rankings,
        matchup_win_pct=matchup_win_pct,
    )


def outcome_weights_public(bracket: Bracket) -> dict[str, Any]:
    weights = get_outcome_weights(bracket)
    return {
        TEAM_RANKINGS_KEY: {
            str(team_id): rank for team_id, rank in sorted(weights.team_rankings.items())
        },
        MATCHUP_ODDS_KEY: {
            str(matchup_id): pct
            for matchup_id, pct in sorted(weights.matchup_win_pct.items())
        },
    }


def set_outcome_weights_on_metadata(
    metadata: dict[str, Any] | None,
    *,
    team_rankings: dict[int, int],
    matchup_win_pct: dict[int, float],
) -> dict[str, Any]:
    meta = dict(metadata) if isinstance(metadata, dict) else {}
    meta[OUTCOME_WEIGHTS_KEY] = {
        TEAM_RANKINGS_KEY: {
            str(team_id): rank for team_id, rank in sorted(team_rankings.items())
        },
        MATCHUP_ODDS_KEY: {
            str(matchup_id): pct
            for matchup_id, pct in sorted(matchup_win_pct.items())
        },
    }
    return meta


def rank_to_rating(rank: int) -> float:
    """Lower FIFA rank (1 = best) maps to a higher rating."""
    return 2100.0 - 50.0 * math.log2(float(max(rank, 1)))


def win_probability_from_rankings(rank_a: int, rank_b: int) -> float:
    """P(team A beats team B) from FIFA-style ranks."""
    return win_probability_from_ratings(rank_to_rating(rank_a), rank_to_rating(rank_b))


def win_probability_from_ratings(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def merge_outcome_weights(
    existing: OutcomeWeights,
    *,
    team_rankings: dict[int, int],
    matchup_win_pct: dict[int, float],
) -> OutcomeWeights:
    """Layer new admin input on top of previously saved weights."""
    merged_rankings = dict(existing.team_rankings)
    merged_rankings.update(team_rankings)
    merged_odds = dict(existing.matchup_win_pct)
    merged_odds.update(matchup_win_pct)
    return OutcomeWeights(
        team_rankings=merged_rankings,
        matchup_win_pct=merged_odds,
    )


def build_effective_ratings(
    weights: OutcomeWeights,
    master: UserBracket,
) -> dict[int, float]:
    """
  FIFA rank ratings adjusted by every stored matchup odds line.

  Earlier-round odds (e.g. QF) keep shaping SF/F likelihood after those games
  finish, until new round odds are entered.
  """
    ratings: dict[int, float] = {
        team_id: rank_to_rating(rank)
        for team_id, rank in weights.team_rankings.items()
    }
    if not ratings or not weights.matchup_win_pct:
        return ratings

    stored_ids = list(weights.matchup_win_pct.keys())
    for m_id, c1, c2 in master.matchup_set.filter(pk__in=stored_ids).values_list(
        "id", "contestant1_id", "contestant2_id"
    ):
        if c1 is None or c2 is None:
            continue
        if c1 not in ratings or c2 not in ratings:
            continue
        p_stored = weights.matchup_win_pct[m_id] / 100.0
        p_model = win_probability_from_ratings(ratings[c1], ratings[c2])
        shift = CALIBRATION_RATING_NUDGE * (p_stored - p_model)
        ratings[c1] += shift
        ratings[c2] -= shift

    return ratings


def _matchup_probability_available(
    matchup: MemMatchup,
    *,
    weights: OutcomeWeights,
    effective_ratings: dict[int, float],
) -> bool:
    if matchup.c1 is None or matchup.c2 is None:
        return False
    db_id = matchup.db_id
    if db_id is not None and db_id in weights.matchup_win_pct:
        return True
    return matchup.c1 in effective_ratings and matchup.c2 in effective_ratings


def current_round_matchup_ids_for_stage(
    master: UserBracket,
    ctx: LeaderboardScoringContext,
) -> tuple[set[int], set[int]]:
    """Return (matchup ids, team ids) for the earliest incomplete main KO stage."""
    ko_stages = [
        s for s in ctx.stages if s.stage_type == BracketStage.StageType.KNOCKOUT
    ]
    main_ko_stages = [
        s for s in ko_stages if not ctx.knockout_by_id[s.pk].is_third_place
    ]
    for stage in main_ko_stages:
        matchups = list(master.matchup_set.filter(stage=stage))
        if not matchups:
            continue
        if all(m.winner_id is not None for m in matchups):
            continue
        matchup_ids: set[int] = set()
        team_ids: set[int] = set()
        for m in matchups:
            if m.contestant1_id is not None:
                team_ids.add(m.contestant1_id)
            if m.contestant2_id is not None:
                team_ids.add(m.contestant2_id)
            if (
                m.winner_id is None
                and m.contestant1_id is not None
                and m.contestant2_id is not None
            ):
                matchup_ids.add(m.pk)
        return matchup_ids, team_ids
    return set(), set()


def current_round_undecided_matchup_ids(
    master: UserBracket,
    ctx: LeaderboardScoringContext,
) -> set[int]:
    """Undecided, paired matchups in the earliest incomplete main knockout stage."""
    matchup_ids, _team_ids = current_round_matchup_ids_for_stage(master, ctx)
    return matchup_ids


def current_round_team_ids(
    master: UserBracket,
    ctx: LeaderboardScoringContext,
) -> set[int]:
    """Teams still playing in the earliest incomplete main knockout stage."""
    _matchup_ids, team_ids = current_round_matchup_ids_for_stage(master, ctx)
    return team_ids


def teams_in_knockout_tree(tree: TreeState) -> set[int]:
    ids: set[int] = set()
    for matchup in tree.matchups:
        if matchup.c1 is not None:
            ids.add(matchup.c1)
        if matchup.c2 is not None:
            ids.add(matchup.c2)
    return ids


def weighted_outcomes_ready(
    weights: OutcomeWeights,
    tree: TreeState,
    *,
    required_team_ids: set[int],
    effective_ratings: dict[int, float],
) -> bool:
    """Likelihood can run when current teams are ranked and every branch has odds."""
    if not weights.team_rankings:
        return False

    if not required_team_ids:
        return False
    if not all(team_id in weights.team_rankings for team_id in required_team_ids):
        return False

    for matchup in tree.matchups:
        if matchup.winner is not None:
            continue
        if matchup.c1 is None or matchup.c2 is None:
            continue
        if not _matchup_probability_available(
            matchup,
            weights=weights,
            effective_ratings=effective_ratings,
        ):
            return False
    return True


def matchup_winner_probability(
    matchup: MemMatchup,
    winner_id: int,
    *,
    weights: OutcomeWeights,
    effective_ratings: dict[int, float],
) -> float | None:
    c1, c2 = matchup.c1, matchup.c2
    if c1 is None or c2 is None or winner_id not in (c1, c2):
        return None

    db_id = matchup.db_id
    if db_id is not None and db_id in weights.matchup_win_pct:
        p_c1 = weights.matchup_win_pct[db_id] / 100.0
    else:
        rating_c1 = effective_ratings.get(c1)
        rating_c2 = effective_ratings.get(c2)
        if rating_c1 is None or rating_c2 is None:
            return None
        p_c1 = win_probability_from_ratings(rating_c1, rating_c2)

    return p_c1 if winner_id == c1 else (1.0 - p_c1)


def show_outcome_weights_for_bracket(bracket: Bracket) -> bool:
    """Set Odds is available once outcomes would be shown (QF+ on master)."""
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket
    from brackets.utils.potential_rank import potential_rank_allowed_for_bracket

    if omit_leaderboard_potential_for_bracket(bracket):
        return False
    return potential_rank_allowed_for_bracket(bracket)


def validate_outcome_weights_payload(
    master: UserBracket,
    ctx: LeaderboardScoringContext,
    *,
    team_rankings: dict[int, int],
    matchup_win_pct: dict[int, float],
    existing: OutcomeWeights | None = None,
) -> str | None:
    """Return an error message when the payload is invalid."""
    merged = merge_outcome_weights(
        existing or _empty_weights(),
        team_rankings=team_rankings,
        matchup_win_pct=matchup_win_pct,
    )

    valid_team_ids = set(
        master.bracket.bracket_contestants.values_list("id", flat=True)
    )
    for team_id, rank in merged.team_rankings.items():
        if team_id not in valid_team_ids:
            return f"Unknown team id {team_id}."
        if rank < 1:
            return "Rankings must be positive integers."

    valid_matchup_ids = set(
        master.matchup_set.filter(stage__stage_type=BracketStage.StageType.KNOCKOUT)
        .values_list("id", flat=True)
    )
    for matchup_id, pct in merged.matchup_win_pct.items():
        if matchup_id not in valid_matchup_ids:
            return f"Unknown matchup id {matchup_id}."
        if pct < 0 or pct > 100:
            return "Odds must be between 0 and 100."

    teams = current_round_team_ids(master, ctx)
    missing_rankings = teams - set(merged.team_rankings)
    if missing_rankings:
        return "Set a ranking for every remaining team."

    return None
