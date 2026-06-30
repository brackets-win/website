"""Per-entry "who do you want to win the next match" picks for the leaderboard.

For the admin-set next match (a single undecided master knockout game between two
contestants X and Y), each submitted entry "wants" whichever of X/Y they took
further in their own bracket — the contestant with the higher *progression score*
(the same per-team score shown on the Stats page). Entries that took both equally
far (a tie, including never picking either) are shown the less popular of X/Y — the
underdog among the players who do have a preference — and nothing when that is tied.
"""

from __future__ import annotations

from brackets.models import UserBracket


def compute_next_match_picks_for_bracket(
    bracket,
) -> dict[int, int | None] | None:
    """Map submitted ``user_bracket_id`` to the wanted ``BracketContestant`` id.

    A value of ``None`` means show nothing for that entry. Returns ``None`` overall
    when there is no valid next match (caller should clear all stored picks).
    """
    from brackets.utils.challenge_stats import progression_scores_by_entry
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

    scores_by_entry = progression_scores_by_entry(bracket, ubs)

    pref: dict[int, str | None] = {}
    for ub in ubs:
        scores = scores_by_entry.get(ub.id, {})
        sx = scores.get(x_id, 0)
        sy = scores.get(y_id, 0)
        if sx > sy:
            pref[ub.id] = "x"
        elif sy > sx:
            pref[ub.id] = "y"
        else:
            pref[ub.id] = None

    return _assign_picks(pref, x_id, y_id)


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

    to_update: list[UserBracket] = []
    for ub in qs:
        pick = picks.get(ub.id)
        if ub.leaderboard_next_match_pick_id != pick:
            ub.leaderboard_next_match_pick_id = pick
            to_update.append(ub)
    if to_update:
        UserBracket.objects.bulk_update(to_update, ["leaderboard_next_match_pick"])
