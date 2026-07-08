"""Challenge winners grouped by each possible master top-four finish."""

from __future__ import annotations

from typing import Any

from brackets.models import BracketChallenge, BracketContestant, UserBracket
from brackets.utils.leaderboard_scoring import load_leaderboard_scoring_context
from brackets.utils.potential_knockout import (
    KnockoutPotentialContext,
    TreeState,
    apply_winner_with_undo,
    competition_ranks_batch,
    completion_totals_vector,
    copy_tree_state,
    find_undecided,
    prepare_knockout_potential,
    restore_undo,
)
from brackets.utils.potential_rank import potential_rank_allowed_for_bracket
from brackets.utils.top_four_picks import TopFourContext, build_top_four_context


def _display_name(contestant_info: dict[int, dict[str, Any]], cid: int) -> str:
    return contestant_info[cid]["display_name"]


def _team_payload(
    cid: int | None,
    contestant_info: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    if cid is None:
        return None
    info = contestant_info.get(cid)
    if info is None:
        return None
    return {
        "bracket_contestant_id": cid,
        "display_name": info["display_name"],
        "image_url": info["image_url"],
    }


def _entry_label(ub: UserBracket) -> str:
    name = (ub.display_name or "").strip()
    if name:
        return name
    return getattr(ub.user, "username", "") or "Player"


def _contestant_info_for_bracket(bracket) -> dict[int, dict[str, Any]]:
    from brackets.api.serializers import contestant_public

    info: dict[int, dict[str, Any]] = {}
    for bc in BracketContestant.objects.filter(bracket=bracket).select_related(
        "contestant"
    ):
        pub = contestant_public(bc)
        info[pub["id"]] = {
            "display_name": pub["display_name"],
            "image_url": pub["image_url"],
        }
    return info


def _master_top_four_ids(
    state: TreeState,
    prepared: KnockoutPotentialContext,
    top_four_ctx: TopFourContext,
    contestant_info: dict[int, dict[str, Any]],
) -> tuple[int | None, int | None, int | None, int | None]:
    scoring = prepared.scoring
    champ_id = ru_id = third_id = fourth_id = None

    if scoring.final_m_idx is not None:
        fm = state.matchups[scoring.final_m_idx]
        if fm.winner is not None and fm.c1 is not None and fm.c2 is not None:
            champ_id = fm.winner
            ru_id = fm.c2 if fm.winner == fm.c1 else fm.c1

    if top_four_ctx.has_third_place and scoring.third_m_idx is not None:
        tm = state.matchups[scoring.third_m_idx]
        if tm.winner is not None and tm.c1 is not None and tm.c2 is not None:
            third_id = tm.winner
            fourth_id = tm.c2 if tm.winner == tm.c1 else tm.c1
    elif top_four_ctx.semifinal_stage is not None:
        ko_stages = scoring.ko_stages
        stage_id_to_idx = {s.pk: i for i, s in enumerate(ko_stages)}
        semi_idx = stage_id_to_idx.get(top_four_ctx.semifinal_stage.pk)
        if semi_idx is not None:
            semi_losers: list[int] = []
            for m_idx in state.stage_matchup_indices[semi_idx]:
                m = state.matchups[m_idx]
                if m.winner is None or m.c1 is None or m.c2 is None:
                    continue
                semi_losers.append(m.c2 if m.winner == m.c1 else m.c1)
            if semi_losers:
                semi_losers.sort(
                    key=lambda cid: _display_name(contestant_info, cid).casefold()
                )
            if len(semi_losers) > 0:
                third_id = semi_losers[0]
            if len(semi_losers) > 1:
                fourth_id = semi_losers[1]

    return champ_id, ru_id, third_id, fourth_id


def _winner_labels_for_completion(
    state: TreeState,
    prepared: KnockoutPotentialContext,
    ubs: list[UserBracket],
) -> list[str]:
    totals = completion_totals_vector(state, prepared.scoring)
    import numpy as np

    ranks = competition_ranks_batch(totals[np.newaxis, :])[0]
    winners = [
        _entry_label(ubs[i])
        for i, rank in enumerate(ranks)
        if int(rank) == 1
    ]
    winners.sort(key=lambda name: name.casefold())
    return winners


def _record_outcome(
    root: dict[str, Any],
    *,
    top_four: tuple[int, int, int, int],
    winners: list[str],
) -> None:
    node = root
    for key in top_four:
        node = node.setdefault(key, {})
    bucket = node.setdefault("_winners", set())
    bucket.update(winners)


def _walk_outcomes(
    prepared: KnockoutPotentialContext,
    ubs: list[UserBracket],
    top_four_ctx: TopFourContext,
    contestant_info: dict[int, dict[str, Any]],
    root: dict[str, Any],
) -> None:
    tree = prepared.tree
    state = copy_tree_state(tree)

    def walk() -> None:
        idx = find_undecided(state)
        if idx is None:
            top_four = _master_top_four_ids(
                state, prepared, top_four_ctx, contestant_info
            )
            if None in top_four:
                return
            winners = _winner_labels_for_completion(state, prepared, ubs)
            if not winners:
                return
            _record_outcome(
                root,
                top_four=top_four,  # type: ignore[arg-type]
                winners=winners,
            )
            return
        m = state.matchups[idx]
        for winner_id in (m.c1, m.c2):
            if winner_id is None:
                continue
            changes = apply_winner_with_undo(state, idx, winner_id)
            walk()
            restore_undo(state, changes)

    walk()


def _subtree_winner_count(node: dict[str, Any]) -> int:
    winners = node.get("_winners")
    if isinstance(winners, set):
        return len(winners)
    total = 0
    for key, child in node.items():
        if key == "_winners":
            continue
        if isinstance(child, dict):
            total += _subtree_winner_count(child)
    return total


def _sort_keys(
    node: dict[str, Any],
    *,
    level: int,
    contestant_info: dict[int, dict[str, Any]],
) -> list[Any]:
    keys = [key for key in node if key != "_winners"]

    def label(key: Any) -> tuple[str, ...]:
        if isinstance(key, tuple):
            return tuple(
                _display_name(contestant_info, cid).casefold() for cid in key
            )
        if isinstance(key, int):
            return (_display_name(contestant_info, key).casefold(),)
        return (str(key).casefold(),)

    return sorted(
        keys,
        key=lambda key: (-_subtree_winner_count(node[key]), label(key)),
    )


def _count_outcome_stats(
    root: dict[str, Any],
) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    counts: dict[str, int] = {}

    def visit(node: dict[str, Any]) -> None:
        nonlocal total
        winners = node.get("_winners")
        if isinstance(winners, set) and winners:
            total += 1
            for name in winners:
                counts[str(name)] = counts.get(str(name), 0) + 1
            return
        for key, child in node.items():
            if key == "_winners" or not isinstance(child, dict):
                continue
            visit(child)

    visit(root)
    winner_odds = [
        {
            "name": name,
            "outcome_count": count,
            "pct": round(100.0 * count / total, 1) if total else 0.0,
        }
        for name, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
    ]
    return total, winner_odds


def _build_outcomes_tree(
    root: dict[str, Any],
    *,
    contestant_info: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not root:
        return []

    def build(node: dict[str, Any], level: int) -> list[dict[str, Any]]:
        if level == 3:
            branches: list[dict[str, Any]] = []
            for fourth_id in _sort_keys(
                node, level=level, contestant_info=contestant_info
            ):
                child = node[fourth_id]
                winners = child.get("_winners") or set()
                if not winners:
                    continue
                team = _team_payload(fourth_id, contestant_info)
                if team is None:
                    continue
                branches.append(
                    {
                        "team": team,
                        "children": [
                            {
                                "winners": sorted(
                                    winners,
                                    key=lambda name: str(name).casefold(),
                                )
                            }
                        ],
                    }
                )
            return branches

        branches: list[dict[str, Any]] = []
        for team_id in _sort_keys(node, level=level, contestant_info=contestant_info):
            child = node[team_id]
            team = _team_payload(team_id, contestant_info)
            if team is None:
                continue
            children = build(child, level + 1)
            if not children:
                continue
            branches.append({"team": team, "children": children})
        return branches

    tree: list[dict[str, Any]] = []
    for champ_id in _sort_keys(root, level=0, contestant_info=contestant_info):
        child = root[champ_id]
        team = _team_payload(champ_id, contestant_info)
        if team is None:
            continue
        children = build(child, level=1)
        if not children:
            continue
        tree.append({"team": team, "children": children})
    return tree


def show_outcomes_tab_for_challenge(challenge: BracketChallenge) -> bool:
    from brackets.utils.challenge_types import CHALLENGE
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket

    if challenge.instance_type != CHALLENGE:
        return False
    if omit_leaderboard_potential_for_bracket(challenge.bracket):
        return False
    return potential_rank_allowed_for_bracket(challenge.bracket)


def build_challenge_outcomes(challenge: BracketChallenge) -> dict[str, Any] | None:
    """Winners per possible master top-four finish for one challenge pool."""
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket

    bracket = challenge.bracket
    if omit_leaderboard_potential_for_bracket(bracket):
        return None
    if not potential_rank_allowed_for_bracket(bracket):
        return None

    ubs = list(
        UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            submitted_at__isnull=False,
        )
        .select_related("user")
        .prefetch_related("matchup_set")
    )
    top_four_ctx = build_top_four_context(bracket)
    if top_four_ctx.final_stage is None:
        return None

    if not ubs:
        return {
            "has_third_place": top_four_ctx.has_third_place,
            "total_outcomes": 0,
            "winner_odds": [],
            "tree": [],
        }

    ctx = load_leaderboard_scoring_context(bracket)
    prepared = prepare_knockout_potential(ctx, ubs)
    if prepared is None:
        return None

    contestant_info = _contestant_info_for_bracket(bracket)
    root: dict[str, Any] = {}
    _walk_outcomes(prepared, ubs, top_four_ctx, contestant_info, root)
    total_outcomes, winner_odds = _count_outcome_stats(root)

    return {
        "has_third_place": top_four_ctx.has_third_place,
        "total_outcomes": total_outcomes,
        "winner_odds": winner_odds,
        "tree": _build_outcomes_tree(
            root,
            contestant_info=contestant_info,
        ),
    }


def _empty_outcomes_payload() -> dict[str, Any]:
    return {
        "has_third_place": False,
        "total_outcomes": 0,
        "winner_odds": [],
        "tree": [],
    }


def _read_outcomes_cache(
    challenge: BracketChallenge,
    entries_revision: int,
    master_revision: int,
) -> dict[str, Any] | None:
    from brackets.utils.challenge_stats import CHALLENGE_OUTCOMES_CACHE_KEY

    meta = challenge.metadata if isinstance(challenge.metadata, dict) else {}
    cache = meta.get(CHALLENGE_OUTCOMES_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    if cache.get("entries_revision") != entries_revision:
        return None
    if cache.get("master_revision") != master_revision:
        return None
    payload = cache.get("payload")
    if not isinstance(payload, dict):
        return None
    if not isinstance(payload.get("tree"), list):
        return None
    if not isinstance(payload.get("winner_odds"), list):
        return None
    if not isinstance(payload.get("total_outcomes"), int):
        return None
    if not isinstance(payload.get("has_third_place"), bool):
        return None
    return payload


def _write_outcomes_cache(
    challenge: BracketChallenge,
    entries_revision: int,
    master_revision: int,
    payload: dict[str, Any],
) -> None:
    from brackets.utils.challenge_stats import CHALLENGE_OUTCOMES_CACHE_KEY

    meta = dict(challenge.metadata) if isinstance(challenge.metadata, dict) else {}
    meta[CHALLENGE_OUTCOMES_CACHE_KEY] = {
        "entries_revision": entries_revision,
        "master_revision": master_revision,
        "payload": payload,
    }
    challenge.metadata = meta
    challenge.save(update_fields=["metadata"])


def get_challenge_outcomes(challenge: BracketChallenge) -> dict[str, Any]:
    """Cached outcomes payload for API responses."""
    from brackets.utils.challenge_stats import (
        get_challenge_stats_master_revision,
        get_challenge_stats_revision,
    )

    if challenge.pk is not None:
        challenge.refresh_from_db(fields=["metadata"])
    entries_revision = get_challenge_stats_revision(challenge)
    master_revision = get_challenge_stats_master_revision(challenge)

    cached = _read_outcomes_cache(challenge, entries_revision, master_revision)
    if cached is not None:
        return cached

    payload = build_challenge_outcomes(challenge)
    if payload is None:
        payload = _empty_outcomes_payload()

    _write_outcomes_cache(
        challenge,
        entries_revision,
        master_revision,
        payload,
    )
    return payload
