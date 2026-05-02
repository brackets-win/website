"""Rebuild later-round knockout slots from first-round picks after a winner is cleared."""

from __future__ import annotations

from django.db import transaction

from brackets.models import BracketStage, Matchup, UserBracket


@transaction.atomic
def clear_matchup_winner_and_downstream(matchup: Matchup) -> None:
    """
    Clear this matchup's winner and undo propagation toward the final: empty the
    matching slot on each next matchup, clear winners on the path, and continue
    until there is no next stage.
    """
    matchup.winner = None
    matchup.save()

    cur = matchup
    nxt = cur.get_next_matchup()
    while nxt:
        if cur.is_team_a():
            nxt.contestant1 = None
        else:
            nxt.contestant2 = None
        nxt.winner = None
        nxt.save()
        cur = nxt
        nxt = cur.get_next_matchup()


@transaction.atomic
def rebuild_knockout_from_first_round(user_bracket: UserBracket) -> None:
    """
    Clear all matchups after the first knockout stage, then re-apply propagate_winner()
    for each first-round matchup that still has a winner.
    Keeps the tree consistent after clearing a pick in any round.
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
