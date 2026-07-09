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
from brackets.utils.outcome_weights import (
    OutcomeWeights,
    build_effective_ratings,
    current_round_team_ids,
    get_outcome_weights,
    matchup_winner_probability,
    weighted_outcomes_ready,
)
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


def _winner_entries_for_completion(
    state: TreeState,
    prepared: KnockoutPotentialContext,
    ubs: list[UserBracket],
) -> list[dict[str, Any]]:
    totals = completion_totals_vector(state, prepared.scoring)
    import numpy as np

    ranks = competition_ranks_batch(totals[np.newaxis, :])[0]
    winners: list[dict[str, Any]] = []
    for i, rank in enumerate(ranks):
        if int(rank) != 1:
            continue
        ub = ubs[i]
        winners.append(
            {
                "user_bracket_id": ub.id,
                "display_name": _entry_label(ub),
                "username": getattr(ub.user, "username", "") or "",
            }
        )
    winners.sort(key=lambda entry: str(entry["display_name"]).casefold())
    return winners


def _record_outcome(
    root: dict[str, Any],
    *,
    top_four: tuple[int, int, int, int],
    winners: list[dict[str, Any]],
) -> None:
    node = root
    for key in top_four:
        node = node.setdefault(key, {})
    bucket: dict[int, dict[str, Any]] = node.setdefault("_winner_entries", {})
    for entry in winners:
        bucket[int(entry["user_bracket_id"])] = entry


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
            winners = _winner_entries_for_completion(state, prepared, ubs)
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


def _path_likelihood_key(*parts: str | int) -> str:
    return ":".join(str(part) for part in parts)


def _accumulate_path_likelihood_at_leaf(
    path_likelihood: dict[str, float],
    top_four: tuple[int | None, int | None, int | None, int | None],
    *,
    has_third_place: bool,
    path_prob: float,
) -> None:
    champ, ru, third, fourth = top_four

    def add(key: str) -> None:
        path_likelihood[key] = path_likelihood.get(key, 0.0) + path_prob

    if champ is None:
        return
    add(_path_likelihood_key("c", champ))
    if ru is None:
        return
    add(_path_likelihood_key("c", champ, "ru", ru))
    if has_third_place:
        if third is None:
            return
        add(_path_likelihood_key("c", champ, "ru", ru, "t", third))
        if fourth is None:
            return
        add(_path_likelihood_key("c", champ, "ru", ru, "t", third, "f", fourth))
    else:
        for team_id in (third, fourth):
            if team_id is None:
                continue
            add(_path_likelihood_key("c", champ, "ru", ru, "s", team_id))


def _path_likelihood_pct(path_likelihood: dict[str, float]) -> dict[str, float]:
    return {
        key: round(100.0 * mass, 1)
        for key, mass in path_likelihood.items()
        if mass > 0
    }


def _accumulate_entry_likelihood(
    prepared: KnockoutPotentialContext,
    ubs: list[UserBracket],
    top_four_ctx: TopFourContext,
    contestant_info: dict[int, dict[str, Any]],
    *,
    weights: OutcomeWeights,
    master: UserBracket,
    required_team_ids: set[int],
    entry_likelihood: dict[int, float],
    team_likelihood: dict[str, float],
) -> bool:
    tree = prepared.tree
    effective_ratings = build_effective_ratings(weights, master)
    if not weighted_outcomes_ready(
        weights,
        tree,
        required_team_ids=required_team_ids,
        effective_ratings=effective_ratings,
    ):
        return False
    state = copy_tree_state(tree)

    def walk(path_prob: float = 1.0) -> bool:
        idx = find_undecided(state)
        if idx is None:
            top_four = _master_top_four_ids(
                state, prepared, top_four_ctx, contestant_info
            )
            if None in top_four:
                return True
            winners = _winner_entries_for_completion(state, prepared, ubs)
            if not winners:
                return True
            for entry in winners:
                entry_id = int(entry["user_bracket_id"])
                entry_likelihood[entry_id] = (
                    entry_likelihood.get(entry_id, 0.0) + path_prob
                )
            _accumulate_path_likelihood_at_leaf(
                team_likelihood,
                top_four,
                has_third_place=top_four_ctx.has_third_place,
                path_prob=path_prob,
            )
            return True

        m = state.matchups[idx]
        branch_probs: list[tuple[int, float]] = []
        for winner_id in (m.c1, m.c2):
            if winner_id is None:
                continue
            branch_prob = matchup_winner_probability(
                m,
                winner_id,
                weights=weights,
                effective_ratings=effective_ratings,
            )
            if branch_prob is None:
                return False
            branch_probs.append((winner_id, branch_prob))

        for winner_id, branch_prob in branch_probs:
            changes = apply_winner_with_undo(state, idx, winner_id)
            if not walk(path_prob * branch_prob):
                restore_undo(state, changes)
                return False
            restore_undo(state, changes)
        return True

    return walk()


def _subtree_winner_count(node: dict[str, Any]) -> int:
    entries = node.get("_winner_entries")
    if isinstance(entries, dict) and entries:
        return len(entries)
    total = 0
    for key, child in node.items():
        if key == "_winner_entries":
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
    keys = [key for key in node if key != "_winner_entries"]

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
    *,
    entry_likelihood: dict[int, float] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    entry_counts: dict[int, int] = {}
    entry_payloads: dict[int, dict[str, Any]] = {}
    likelihood_total = 0.0

    def visit(node: dict[str, Any]) -> None:
        nonlocal total, likelihood_total
        entries = node.get("_winner_entries")
        if isinstance(entries, dict) and entries:
            total += 1
            for entry in entries.values():
                entry_id = int(entry["user_bracket_id"])
                entry_counts[entry_id] = entry_counts.get(entry_id, 0) + 1
                if entry_id not in entry_payloads:
                    entry_payloads[entry_id] = entry
            return
        for key, child in node.items():
            if key == "_winner_entries" or not isinstance(child, dict):
                continue
            visit(child)

    visit(root)

    if entry_likelihood:
        likelihood_total = sum(entry_likelihood.values())

    winner_odds: list[dict[str, Any]] = []
    for entry_id, count in sorted(
        entry_counts.items(),
        key=lambda item: (
            -item[1],
            str(entry_payloads[item[0]].get("display_name") or "").casefold(),
        ),
    ):
        row: dict[str, Any] = {
            "entry": entry_payloads[entry_id],
            "outcome_count": count,
            "pct": round(100.0 * count / total, 1) if total else 0.0,
        }
        if entry_likelihood and likelihood_total > 0:
            mass = entry_likelihood.get(entry_id, 0.0)
            row["likelihood"] = round(100.0 * mass / likelihood_total, 1)
        winner_odds.append(row)
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
                entries_map = child.get("_winner_entries") or {}
                if not entries_map:
                    continue
                team = _team_payload(fourth_id, contestant_info)
                if team is None:
                    continue
                entries = sorted(
                    entries_map.values(),
                    key=lambda entry: str(entry["display_name"]).casefold(),
                )
                branches.append(
                    {
                        "team": team,
                        "children": [{"winners": entries}],
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


def show_outcomes_tab_for_challenge(
    challenge: BracketChallenge,
    *,
    scoring_ctx=None,
) -> bool:
    from brackets.utils.challenge_types import CHALLENGE
    from brackets.utils.group_results_mode import omit_leaderboard_potential_for_bracket
    from brackets.utils.potential_rank import potential_rank_allowed_for_context

    if challenge.instance_type != CHALLENGE:
        return False
    if omit_leaderboard_potential_for_bracket(challenge.bracket):
        return False
    if scoring_ctx is not None:
        return potential_rank_allowed_for_context(scoring_ctx)
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
    weights = get_outcome_weights(bracket)
    required_team_ids = current_round_team_ids(ctx.master, ctx)
    entry_likelihood: dict[int, float] = {}
    team_likelihood: dict[str, float] = {}
    weighted_ok = _accumulate_entry_likelihood(
        prepared,
        ubs,
        top_four_ctx,
        contestant_info,
        weights=weights,
        master=ctx.master,
        required_team_ids=required_team_ids,
        entry_likelihood=entry_likelihood,
        team_likelihood=team_likelihood,
    )
    total_outcomes, winner_odds = _count_outcome_stats(
        root,
        entry_likelihood=entry_likelihood if weighted_ok else None,
    )

    payload: dict[str, Any] = {
        "has_third_place": top_four_ctx.has_third_place,
        "total_outcomes": total_outcomes,
        "winner_odds": winner_odds,
        "tree": _build_outcomes_tree(
            root,
            contestant_info=contestant_info,
        ),
    }
    if weighted_ok and team_likelihood:
        payload["team_likelihood"] = _path_likelihood_pct(team_likelihood)
    return payload


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
    odds = payload.get("winner_odds")
    if odds and not isinstance(odds[0], dict):
        return None
    if odds and "entry" not in odds[0]:
        return None
    if not _outcomes_tree_has_entry_winners(payload.get("tree")):
        return None
    return payload


def _outcomes_tree_has_entry_winners(tree: Any) -> bool:
    if not isinstance(tree, list):
        return False
    if not tree:
        return True

    def walk(nodes: list[Any]) -> bool:
        for node in nodes:
            if not isinstance(node, dict):
                return False
            if "winners" in node:
                winners = node.get("winners")
                if not isinstance(winners, list) or not winners:
                    return False
                first = winners[0]
                return isinstance(first, dict) and "user_bracket_id" in first
            children = node.get("children")
            if not isinstance(children, list) or not walk(children):
                return False
        return True

    return walk(tree)


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
    from brackets.utils.single_flight import single_flight

    if challenge.pk is not None:
        challenge.refresh_from_db(fields=["metadata"])
    entries_revision = get_challenge_stats_revision(challenge)
    master_revision = get_challenge_stats_master_revision(challenge)

    cached = _read_outcomes_cache(challenge, entries_revision, master_revision)
    if cached is not None:
        return cached

    def _compute() -> dict[str, Any]:
        # Re-check cache inside the flight in case a peer just wrote it.
        if challenge.pk is not None:
            challenge.refresh_from_db(fields=["metadata"])
        again = _read_outcomes_cache(
            challenge, entries_revision, master_revision
        )
        if again is not None:
            return again
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

    return single_flight(
        f"outcomes:{challenge.pk}:{entries_revision}:{master_revision}",
        _compute,
    )
