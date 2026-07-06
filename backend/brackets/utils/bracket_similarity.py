"""Group submitted brackets by shared top-eight knockout picks."""

from __future__ import annotations

from typing import Any

from brackets.models import Bracket, BracketStage, UserBracket
from brackets.utils.top_four_picks import TopFourContext, build_top_four_context, top_four_bracket_contestants


def _stage_before(
    main_knockout_stages: list[BracketStage],
    target: BracketStage | None,
) -> BracketStage | None:
    if target is None:
        return None
    prev: BracketStage | None = None
    for stage in main_knockout_stages:
        if stage.id == target.id:
            return prev
        prev = stage
    return None


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


def _top_four_ids(
    ub: UserBracket,
    ctx: TopFourContext,
    contestant_info: dict[int, dict[str, Any]],
) -> tuple[int | None, int | None, int | None, int | None]:
    champion, runner_up, third, fourth = top_four_bracket_contestants(ub, ctx)
    if not ctx.has_third_place and ctx.semifinal_stage is not None:
        semi: list[int] = []
        for bc in (third, fourth):
            if bc is not None:
                semi.append(bc.id)
        semi.sort(key=lambda cid: _display_name(contestant_info, cid).casefold())
        third_id = semi[0] if len(semi) > 0 else None
        fourth_id = semi[1] if len(semi) > 1 else None
        return (
            champion.id if champion else None,
            runner_up.id if runner_up else None,
            third_id,
            fourth_id,
        )
    return (
        champion.id if champion else None,
        runner_up.id if runner_up else None,
        third.id if third else None,
        fourth.id if fourth else None,
    )


def _quarter_final_loser_ids(
    ub: UserBracket,
    quarter_final_stage: BracketStage,
    contestant_info: dict[int, dict[str, Any]],
) -> list[int]:
    losers: list[int] = []
    for matchup in ub.matchup_set.filter(stage=quarter_final_stage).order_by("position"):
        if not matchup.winner_id:
            continue
        loser = matchup.get_loser()
        if loser is not None:
            losers.append(loser.id)
    losers.sort(key=lambda cid: _display_name(contestant_info, cid).casefold())
    return losers


def _entry_label(ub: UserBracket) -> str:
    name = (ub.display_name or "").strip()
    if name:
        return name
    return getattr(ub.user, "username", "") or "Player"


def _subtree_count(node: dict[str, Any]) -> int:
    entries = node.get("_entries")
    if isinstance(entries, list):
        return len(entries)
    total = 0
    for key, child in node.items():
        if key == "_entries":
            continue
        if isinstance(child, dict):
            total += _subtree_count(child)
    return total


def _sort_keys(
    node: dict[str, Any],
    *,
    level: int,
    contestant_info: dict[int, dict[str, Any]],
) -> list[Any]:
    keys = [key for key in node if key != "_entries"]

    def label(key: Any) -> tuple[str, ...]:
        if level == 4 and isinstance(key, tuple):
            return tuple(_display_name(contestant_info, cid).casefold() for cid in key)
        if isinstance(key, int):
            return (_display_name(contestant_info, key).casefold(),)
        return (str(key).casefold(),)

    return sorted(
        keys,
        key=lambda key: (-_subtree_count(node[key]), label(key)),
    )


def _build_nested_tree(
    node: dict[str, Any],
    *,
    level: int,
    contestant_info: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    if "_entries" in node and len(node) == 1:
        return []

    if level == 4:
        leaves: list[dict[str, Any]] = []
        for qf_key in _sort_keys(node, level=level, contestant_info=contestant_info):
            entries = node[qf_key].get("_entries") or []
            if not entries:
                continue
            qf_ids = list(qf_key) if isinstance(qf_key, tuple) else []
            quarter_finalists = [
                payload
                for cid in qf_ids
                if (payload := _team_payload(cid, contestant_info)) is not None
            ]
            leaves.append(
                {
                    "quarter_finalists": quarter_finalists,
                    "count": len(entries),
                    "entries": entries,
                }
            )
        return leaves

    branches: list[dict[str, Any]] = []
    for team_id in _sort_keys(node, level=level, contestant_info=contestant_info):
        child = node[team_id]
        team = _team_payload(team_id, contestant_info)
        if team is None:
            continue
        children = _build_nested_tree(
            child,
            level=level + 1,
            contestant_info=contestant_info,
        )
        if not children:
            continue
        branches.append(
            {
                "team": team,
                "count": _subtree_count(child),
                "children": children,
            }
        )
    return branches


def build_bracket_similarity_tree(
    user_brackets: list[UserBracket],
    *,
    bracket: Bracket,
    main_knockout_stages: list[BracketStage],
    contestant_info: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    """Nested tree of entries grouped by top-eight knockout picks."""
    ctx = build_top_four_context(bracket)
    if ctx.final_stage is None or ctx.semifinal_stage is None:
        return None

    quarter_final_stage = _stage_before(main_knockout_stages, ctx.semifinal_stage)
    if quarter_final_stage is None:
        return None

    root: dict[str, Any] = {}
    for ub in user_brackets:
        champ_id, ru_id, third_id, fourth_id = _top_four_ids(ub, ctx, contestant_info)
        if None in (champ_id, ru_id, third_id, fourth_id):
            continue
        qf_ids = _quarter_final_loser_ids(ub, quarter_final_stage, contestant_info)
        if len(qf_ids) != 4:
            continue

        qf_key = tuple(qf_ids)
        path = (champ_id, ru_id, third_id, fourth_id, qf_key)
        node = root
        for key in path:
            node = node.setdefault(key, {})
        node.setdefault("_entries", []).append(
            {
                "user_bracket_id": ub.id,
                "display_name": _entry_label(ub),
                "username": getattr(ub.user, "username", "") or "",
            }
        )

    if not root:
        return {
            "has_third_place": ctx.has_third_place,
            "tree": [],
        }

    for entries in _iter_entry_lists(root):
        entries.sort(key=lambda e: e["display_name"].casefold())

    tree = _build_nested_tree(root, level=0, contestant_info=contestant_info)
    return {
        "has_third_place": ctx.has_third_place,
        "tree": tree,
    }


def _iter_entry_lists(node: dict[str, Any]):
    if "_entries" in node:
        yield node["_entries"]
    for key, child in node.items():
        if key == "_entries":
            continue
        if isinstance(child, dict):
            yield from _iter_entry_lists(child)
