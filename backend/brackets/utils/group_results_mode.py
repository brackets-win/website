"""Bracket metadata flag for provisional vs final group-stage results."""

from __future__ import annotations

from typing import Any, Literal

GroupResultsMode = Literal["live", "confirmed"]

GROUP_RESULTS_MODE_KEY = "group_results_mode"
VALID_GROUP_RESULTS_MODES = frozenset({"live", "confirmed"})


def parse_group_results_mode(raw: Any) -> GroupResultsMode:
    if raw == "live":
        return "live"
    return "confirmed"


def group_results_mode_from_metadata(metadata: Any) -> GroupResultsMode:
    if not isinstance(metadata, dict):
        return "confirmed"
    return parse_group_results_mode(metadata.get(GROUP_RESULTS_MODE_KEY))


def set_group_results_mode_on_metadata(
    metadata: Any, mode: GroupResultsMode
) -> dict[str, Any]:
    base = dict(metadata) if isinstance(metadata, dict) else {}
    base[GROUP_RESULTS_MODE_KEY] = mode
    return base


def show_live_group_results_note_for_bracket(bracket) -> bool:
    """True when group UI exists and bracket metadata marks results as live."""
    from brackets.api.serializers import bracket_groups_preview
    from brackets.models import BracketStage

    has_group_stage = bracket.stages.filter(
        stage_type=BracketStage.StageType.GROUP
    ).exists()
    if not has_group_stage:
        return False
    if not bracket_groups_preview(bracket):
        return False
    return group_results_mode_from_metadata(bracket.metadata) == "live"


def master_has_group_results(bracket) -> bool:
    """True when the master bracket has at least one filled group-position slot."""
    master = bracket.get_master_bracket()
    if master is None:
        return False
    gp = (master.metadata or {}).get("group_positions") or {}
    if not isinstance(gp, dict) or not gp:
        return False
    for row in gp.values():
        if not isinstance(row, dict):
            continue
        for value in row.values():
            if value is not None and value != "":
                return True
    return False


def master_bracket_is_fully_resolved(bracket) -> bool:
    """True when every playable master knockout game has a winner.

    Uses the same branchable-undecided count as potential scoring: ``0`` means
    the first knockout round is seeded and nothing remains to project.
    ``None`` means the bracket is not scoreable yet (e.g. R32 unseeded).
    """
    from brackets.utils.potential_knockout import count_branchable_for_bracket

    count = count_branchable_for_bracket(bracket)
    return count is not None and count == 0


def omit_leaderboard_potential_for_bracket(bracket) -> bool:
    """Hide potential until group results are confirmed, or when the master is finished.

    For group→knockout brackets, skip calc and leaderboard columns until the admin
    marks group results as confirmed *and* the master has group positions filled.
    Knockout-only brackets keep potential (unless the master is fully resolved).
    """
    from brackets.models import BracketStage

    if master_bracket_is_fully_resolved(bracket):
        return True

    has_group_stage = bracket.stages.filter(
        stage_type=BracketStage.StageType.GROUP
    ).exists()
    if not has_group_stage:
        return False

    if group_results_mode_from_metadata(bracket.metadata) != "confirmed":
        return True
    return not master_has_group_results(bracket)
