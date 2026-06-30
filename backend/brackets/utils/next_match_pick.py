"""Per-entry "who do you want to win the next match" picks for the leaderboard.

For the admin-set next match (a single undecided master knockout game between two
contestants X and Y), each submitted entry "wants" whichever outcome gives them a
better *potential rank*. When potential rank can't be enumerated yet, we fall back
to *potential points*. Entries that are indifferent (both outcomes reach the same
best result) are shown the less popular of X/Y — the underdog among the players who
do have a preference — and nothing at all when that is tied.
"""

from __future__ import annotations

from django.db import transaction

from brackets.models import BracketContestant, BracketStage, Matchup, UserBracket


def compute_next_match_picks_for_bracket(
    bracket,
) -> dict[int, int | None] | None:
    """Map submitted ``user_bracket_id`` to the wanted ``BracketContestant`` id.

    A value of ``None`` means show nothing for that entry. Returns ``None`` overall
    when there is no valid next match (caller should clear all stored picks).
    """
    from brackets.utils.next_match import get_next_match_matchup

    m = get_next_match_matchup(bracket)
    if m is None:
        return None

    x_id = m.contestant1_id
    y_id = m.contestant2_id

    ubs = list(
        UserBracket.objects.filter(
            bracket=bracket,
            is_master=False,
            submitted_at__isnull=False,
        )
    )
    if not ubs:
        return {}

    pref = _rank_based_pref(bracket, m, x_id, y_id, ubs)
    if pref is None:
        pref = _points_based_pref(bracket, m, x_id, y_id, ubs)

    return _assign_picks(pref, x_id, y_id)


def _rank_based_pref(
    bracket, m: Matchup, x_id: int, y_id: int, ubs: list[UserBracket]
) -> dict[int, str | None] | None:
    """Preference ('x'/'y'/None) by best potential rank, or None if not enumerable."""
    from brackets.utils.potential_rank import (
        compute_next_match_side_ranks_for_bracket,
    )

    side_ranks = compute_next_match_side_ranks_for_bracket(
        bracket, m.stage_id, m.position, x_id
    )
    if side_ranks is None:
        return None

    pref: dict[int, str | None] = {}
    for ub in ubs:
        rx, ry = side_ranks.get(ub.id, (None, None))
        if rx is None and ry is None:
            pref[ub.id] = None
        elif ry is None:
            pref[ub.id] = "x"
        elif rx is None:
            pref[ub.id] = "y"
        elif rx < ry:
            pref[ub.id] = "x"
        elif ry < rx:
            pref[ub.id] = "y"
        else:
            pref[ub.id] = None
    return pref


def _points_based_pref(
    bracket, m: Matchup, x_id: int, y_id: int, ubs: list[UserBracket]
) -> dict[int, str | None]:
    """Preference ('x'/'y'/None) by best potential points (rank fallback)."""
    ub_ids = [ub.id for ub in ubs]
    pot_x = _potential_with_winner(bracket, m.id, x_id, ub_ids)
    pot_y = _potential_with_winner(bracket, m.id, y_id, ub_ids)

    pref: dict[int, str | None] = {}
    for ub_id in ub_ids:
        px = pot_x.get(ub_id)
        py = pot_y.get(ub_id)
        if px is None or py is None or px == py:
            pref[ub_id] = None
        elif px > py:
            pref[ub_id] = "x"
        else:
            pref[ub_id] = "y"
    return pref


class _Rollback(Exception):
    def __init__(self, value):
        self.value = value


def _potential_with_winner(
    bracket, matchup_id: int, winner_contestant_id: int, ub_ids: list[int]
) -> dict[int, int | None]:
    """Potential points per entry with the next match hypothetically decided.

    Applies the winner (propagating downstream on the master in a transaction that
    is always rolled back) and recomputes each entry's potential score.
    """
    from brackets.api.serializers import bracket_groups_preview
    from brackets.utils.leaderboard_scoring import (
        load_leaderboard_scoring_context,
    )
    from brackets.utils.potential_score import calculate_potential_score

    try:
        with transaction.atomic():
            m = Matchup.objects.get(pk=matchup_id)
            m.winner = BracketContestant.objects.get(pk=winner_contestant_id)
            m.save()

            ctx = load_leaderboard_scoring_context(bracket)
            master = ctx.master
            main_ko_stages = [
                s
                for s in ctx.stages
                if s.stage_type == BracketStage.StageType.KNOCKOUT
                and not ctx.knockout_by_id[s.pk].is_third_place
            ]
            groups_preview = bracket_groups_preview(bracket)

            out: dict[int, int | None] = {}
            for ub in UserBracket.objects.filter(pk__in=ub_ids).prefetch_related(
                "matchup_set"
            ):
                out[ub.id] = calculate_potential_score(
                    ub,
                    master=master,
                    main_ko_stages=main_ko_stages,
                    groups_preview=groups_preview,
                    knockout_by_id=ctx.knockout_by_id,
                )
            raise _Rollback(out)
    except _Rollback as rollback:
        return rollback.value


def _assign_picks(
    pref: dict[int, str | None], x_id: int, y_id: int
) -> dict[int, int | None]:
    x_count = sum(1 for v in pref.values() if v == "x")
    y_count = sum(1 for v in pref.values() if v == "y")
    if x_count < y_count:
        less_popular: int | None = x_id
    elif y_count < x_count:
        less_popular = y_id
    else:
        # Tie (including everyone indifferent): no clear underdog — show nothing.
        less_popular = None

    out: dict[int, int | None] = {}
    for ub_id, choice in pref.items():
        if choice == "x":
            out[ub_id] = x_id
        elif choice == "y":
            out[ub_id] = y_id
        else:
            out[ub_id] = less_popular
    return out


def persist_next_match_picks_for_bracket(bracket) -> None:
    """Compute and store next-match picks on all submitted entries."""
    from brackets.utils.next_match import show_next_match_for_bracket

    qs = UserBracket.objects.filter(
        bracket=bracket,
        is_master=False,
        submitted_at__isnull=False,
    )

    if not show_next_match_for_bracket(bracket):
        qs.exclude(leaderboard_next_match_pick__isnull=True).update(
            leaderboard_next_match_pick=None
        )
        return

    picks = compute_next_match_picks_for_bracket(bracket)
    if picks is None:
        qs.exclude(leaderboard_next_match_pick__isnull=True).update(
            leaderboard_next_match_pick=None
        )
        return

    for ub in qs:
        pick = picks.get(ub.id)
        if ub.leaderboard_next_match_pick_id != pick:
            ub.leaderboard_next_match_pick_id = pick
            ub.save(update_fields=["leaderboard_next_match_pick"])
