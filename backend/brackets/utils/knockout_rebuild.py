"""Knockout pick propagation: remove one team from advancement paths without wiping other picks."""

from __future__ import annotations

from django.db import transaction

from brackets.models import BracketStage, Matchup, UserBracket


def _remove_team_from_sourced_feeds(feeder: Matchup, team_id: int) -> None:
    """Third-place (and other explicit source rows) fed from ``feeder``."""
    for downstream in feeder.feeds_team_a_to.all():
        if downstream.contestant1_id != team_id and downstream.winner_id != team_id:
            continue
        if downstream.contestant1_id == team_id:
            downstream.contestant1 = None
        if downstream.winner_id == team_id:
            downstream.winner = None
        downstream.save(update_fields=["contestant1", "winner"])
        remove_team_from_knockout_path(downstream, team_id)

    for downstream in feeder.feeds_team_b_to.all():
        if downstream.contestant2_id != team_id and downstream.winner_id != team_id:
            continue
        if downstream.contestant2_id == team_id:
            downstream.contestant2 = None
        if downstream.winner_id == team_id:
            downstream.winner = None
        downstream.save(update_fields=["contestant2", "winner"])
        remove_team_from_knockout_path(downstream, team_id)


def _remove_loser_from_sourced_feeds(feeder: Matchup, loser_id: int) -> None:
    """Clear loser slots from downstream matchups that use the loser (source_uses_winner=False)."""
    for downstream in feeder.feeds_team_a_to.filter(source_a_uses_winner=False):
        if downstream.contestant1_id != loser_id and downstream.winner_id != loser_id:
            continue
        if downstream.contestant1_id == loser_id:
            downstream.contestant1 = None
        if downstream.winner_id == loser_id:
            downstream.winner = None
        downstream.save(update_fields=["contestant1", "winner"])

    for downstream in feeder.feeds_team_b_to.filter(source_b_uses_winner=False):
        if downstream.contestant2_id != loser_id and downstream.winner_id != loser_id:
            continue
        if downstream.contestant2_id == loser_id:
            downstream.contestant2 = None
        if downstream.winner_id == loser_id:
            downstream.winner = None
        downstream.save(update_fields=["contestant2", "winner"])


@transaction.atomic
def remove_team_from_knockout_path(from_matchup: Matchup, team_id: int) -> None:
    """
    Remove ``team_id`` only where it appears along this matchup's winner path:
    the fed slot in the next round, then that team's winner picks further on.
    Other teams' slots and picks on the same game or other games are untouched.
    """
    cur = from_matchup
    nxt = cur.get_next_matchup()
    while nxt:
        touched = False
        if cur.is_team_a():
            if nxt.contestant1_id == team_id:
                nxt.contestant1 = None
                touched = True
        else:
            if nxt.contestant2_id == team_id:
                nxt.contestant2 = None
                touched = True
        if nxt.winner_id == team_id:
            nxt.winner = None
            touched = True
        if not touched:
            break
        nxt.save(update_fields=["contestant1", "contestant2", "winner"])
        cur = nxt
        nxt = cur.get_next_matchup()


@transaction.atomic
def clear_matchup_winner_and_downstream(matchup: Matchup) -> None:
    """Clear this game's winner and remove only that team from later rounds."""
    team_id = matchup.winner_id
    matchup.winner = None
    matchup.save(update_fields=["winner"])
    if team_id:
        remove_team_from_knockout_path(matchup, team_id)
        _remove_team_from_sourced_feeds(matchup, team_id)
        # Also clear the loser from any loser-fed downstream matchups (e.g. third place)
        loser_id = (
            matchup.contestant2_id
            if matchup.contestant1_id == team_id
            else matchup.contestant1_id
        )
        if loser_id:
            _remove_loser_from_sourced_feeds(matchup, loser_id)


@transaction.atomic
def rebuild_knockout_from_first_round(user_bracket: UserBracket) -> None:
    """
    Clear all matchups after the first knockout stage, then re-apply propagate_winner()
    for each first-round matchup that still has a winner.
    Used when group→knockout sync rebuilds the tree, not for a single pick clear.
    """
    bracket = user_bracket.bracket
    ko_stages = list(
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT).order_by(
            "order"
        )
    )
    if len(ko_stages) < 2:
        return

    first = ko_stages[0]
    Matchup.objects.filter(
        user_bracket=user_bracket,
        stage__order__gt=first.order,
    ).update(contestant1=None, contestant2=None, winner=None)

    for m in Matchup.objects.filter(
        user_bracket=user_bracket,
        stage=first,
    ).order_by("position"):
        if m.winner_id:
            m.propagate_winner()
