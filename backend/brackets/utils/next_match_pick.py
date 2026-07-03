"""Per-entry "who do you want to win the next match" picks for the leaderboard.

For the admin-set next match (a single undecided master knockout game between two
contestants X and Y), each submitted entry "wants" whichever of X/Y they took
further in their own bracket — the contestant who reached the deeper knockout round.
The third-place match breaks the tie among semifinal losers (winning it ranks above
losing it, both below the final's runner-up). Group placement is ignored. Entries
that took both teams equally far (including never advancing either) are shown the
less popular of X/Y — the underdog among players who do have a preference — and
nothing when that is tied too.
"""

from __future__ import annotations

from brackets.models import BracketStage, KnockoutStage, UserBracket


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

    depths_by_entry = _knockout_depths_by_entry(bracket, ubs, {x_id, y_id})

    pref: dict[int, str | None] = {}
    for ub in ubs:
        depths = depths_by_entry.get(ub.id, {})
        dx = depths.get(x_id, 0.0)
        dy = depths.get(y_id, 0.0)
        if dx > dy:
            pref[ub.id] = "x"
        elif dy > dx:
            pref[ub.id] = "y"
        else:
            pref[ub.id] = None

    return _assign_picks(pref, x_id, y_id)


def _knockout_depths_by_entry(
    bracket, ubs: list[UserBracket], team_ids: set[int]
) -> dict[int, dict[int, float]]:
    """Per entry: ``{team_id: knockout depth}`` for the requested teams.

    Depth is the deepest knockout round the team reached in that entry's bracket
    (final = ``n``, semifinal = ``n-1``, ...). The champion is bumped to ``n+1`` and
    the third-place-match winner to ``(n-1)+0.5`` so the top placements order as
    champion > runner-up > third place > fourth place. Group results don't count.
    """
    from brackets.utils.sync_group_knockout import contestants_in_stage_for_scoring

    knockout_stages = list(
        bracket.stages.filter(
            stage_type=BracketStage.StageType.KNOCKOUT
        ).order_by("order")
    )
    third_place_ids = {
        ks.pk
        for ks in KnockoutStage.objects.filter(bracket=bracket, is_third_place=True)
    }
    main_ko_stages = [s for s in knockout_stages if s.id not in third_place_ids]
    third_place_stage = next(
        (s for s in knockout_stages if s.id in third_place_ids), None
    )
    final_stage = main_ko_stages[-1] if main_ko_stages else None
    n = len(main_ko_stages)

    out: dict[int, dict[int, float]] = {}
    for ub in ubs:
        depths = {tid: 0.0 for tid in team_ids}
        for level, stage in enumerate(main_ko_stages, start=1):
            hits = contestants_in_stage_for_scoring(ub, stage)
            for tid in team_ids:
                if tid in hits:
                    depths[tid] = float(level)

        if third_place_stage is not None:
            tp = ub.matchup_set.filter(stage=third_place_stage, position=1).first()
            if tp is not None and tp.winner_id in depths:
                depths[tp.winner_id] = float(max(n - 1, 0)) + 0.5

        if final_stage is not None:
            fm = ub.matchup_set.filter(stage=final_stage, position=1).first()
            if fm is not None and fm.winner_id in depths:
                depths[fm.winner_id] = float(n + 1)

        out[ub.id] = depths
    return out


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


def persist_next_match_pick_for_user_bracket(ub: UserBracket) -> None:
    """Compute and store the next-match pick for one submitted entry.

    Uses preferences across all submitted entries for tie-breaking but only
    writes ``leaderboard_next_match_pick`` on ``ub``. No-op when the next-match
    column is not active for this bracket.
    """
    if ub.is_master or ub.submitted_at is None:
        return

    bracket = ub.bracket
    from brackets.utils.next_match import show_next_match_for_bracket

    if not show_next_match_for_bracket(bracket):
        if ub.leaderboard_next_match_pick_id is not None:
            UserBracket.objects.filter(pk=ub.pk).update(
                leaderboard_next_match_pick=None
            )
        return

    picks = compute_next_match_picks_for_bracket(bracket)
    if picks is None:
        if ub.leaderboard_next_match_pick_id is not None:
            UserBracket.objects.filter(pk=ub.pk).update(
                leaderboard_next_match_pick=None
            )
        return

    pick = picks.get(ub.id)
    if ub.leaderboard_next_match_pick_id != pick:
        UserBracket.objects.filter(pk=ub.pk).update(
            leaderboard_next_match_pick=pick
        )
