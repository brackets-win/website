"""Read group-stage advancement rules from the bracket's linked GroupStage row."""

from __future__ import annotations

from brackets.models import Bracket, BracketStage, GroupStage, KnockoutStage

PICKING_ALL = GroupStage.GroupPositionPicking.ALL
PICKING_QUALIFYING_ONLY = GroupStage.GroupPositionPicking.QUALIFYING_ONLY


def get_group_stage(bracket: Bracket) -> GroupStage | None:
    stage = (
        bracket.stages.filter(stage_type=BracketStage.StageType.GROUP)
        .order_by("order")
        .first()
    )
    if stage is None:
        return None
    return GroupStage.objects.get(pk=stage.pk)


def is_qualifying_only_picking(gs: GroupStage) -> bool:
    return (
        getattr(gs, "group_position_picking", PICKING_ALL)
        == PICKING_QUALIFYING_ONLY
    )


def group_stage_pick_requirements(
    gs: GroupStage,
) -> tuple[int, int]:
    """
    Return ``(placement_ranks_required, third_place_advancer_count)``.

    * ``placement_ranks_required`` — each group must have ranks ``1`` … ``N`` filled.
    * ``third_place_advancer_count`` — how many third-place teams the user picks
      when ``contestants_advancing`` exceeds ``groups × qualifying_per_group``.

    Under ``qualifying_only``, users only fill the direct qualifying ranks (``q``);
    third-place advancers are chosen from the remaining unplaced teams, so ``N``
    stays ``q`` even when a third-place pool exists.
    """
    q = gs.contestants_qualifying_per_group
    n_groups = gs.number_of_groups
    direct = n_groups * q
    advancing = resolve_group_contestants_advancing(gs)
    extra = advancing - direct
    if extra <= 0:
        return q, 0

    if is_qualifying_only_picking(gs):
        return q, extra

    # e.g. WC "all": 2 qualify per group + place a 3rd, then pick 8 of those 12
    return q + 1, extra


def group_stage_scorable_ranks(gs: GroupStage) -> int:
    """
    How many finish positions per group earn ``points_per_exact_position``
    from ``group_positions`` (and count toward per-group potential slots).

    Under ``qualifying_only``, correctly matched ``third_place_advancers`` also
    earn exact-placement points — see ``group_stage_exact_placement_count``.
    """
    if is_qualifying_only_picking(gs):
        ranks, _ = group_stage_pick_requirements(gs)
        return ranks
    if gs.number_of_groups <= 0:
        return 0
    return gs.number_of_contestants // gs.number_of_groups


def group_stage_exact_placement_count(gs: GroupStage) -> int:
    """
    Total exact-placement scoring opportunities for a perfect group score.

    Per-group scorable ranks × groups, plus under ``qualifying_only`` each
    third-place rail pick (top-n advancing thirds) that can match the master.
    """
    ranks = group_stage_scorable_ranks(gs)
    total = ranks * gs.number_of_groups
    if is_qualifying_only_picking(gs):
        _, third = group_stage_pick_requirements(gs)
        total += third
    return total


def matching_third_place_advancer_ids(
    user_metadata: dict | None,
    master_metadata: dict | None,
) -> set[int]:
    """Contestant ids present in both user and master ``third_place_advancers``."""
    user_tp = (user_metadata or {}).get("third_place_advancers") or []
    master_tp = (master_metadata or {}).get("third_place_advancers") or []
    if not isinstance(user_tp, list) or not isinstance(master_tp, list):
        return set()
    try:
        master_tp_ids = {int(x) for x in master_tp if x is not None}
    except (TypeError, ValueError):
        return set()
    matched: set[int] = set()
    for cid in user_tp:
        if cid is None:
            continue
        try:
            cid_int = int(cid)
        except (TypeError, ValueError):
            continue
        if cid_int in master_tp_ids:
            matched.add(cid_int)
    return matched


def resolve_group_contestants_advancing(
    gs: GroupStage,
    bracket: Bracket | None = None,
) -> int:
    """
    Total teams leaving the group stage (direct qualifiers + third-place pool).

    Admin saves must not collapse this to ``groups × qualifying`` when the bracket
    also sends third-place teams into the Round of 32.
    """
    if bracket is None:
        bracket = gs.bracket
    direct = gs.number_of_groups * gs.contestants_qualifying_per_group
    current = gs.contestants_advancing
    if current is not None and current > direct:
        return current

    uses_third_pool = bool(
        bracket.has_third_place_match or gs.remaining_spots_strategy
    )
    if not uses_third_pool:
        return direct

    for stage in bracket.stages.filter(
        stage_type=BracketStage.StageType.KNOCKOUT
    ).order_by("order"):
        ks = KnockoutStage.objects.filter(pk=stage.pk).first()
        if ks and (ks.is_third_place or ks.is_final):
            continue
        n = stage.number_of_contestants
        if n and n > direct:
            return n

    if gs.remaining_spots_strategy:
        return direct + 8
    return direct
