"""Read group-stage advancement rules from the bracket's linked GroupStage row."""

from __future__ import annotations

from brackets.models import Bracket, BracketStage, GroupStage, KnockoutStage


def get_group_stage(bracket: Bracket) -> GroupStage | None:
    stage = (
        bracket.stages.filter(stage_type=BracketStage.StageType.GROUP)
        .order_by("order")
        .first()
    )
    if stage is None:
        return None
    return GroupStage.objects.get(pk=stage.pk)


def group_stage_pick_requirements(
    gs: GroupStage,
) -> tuple[int, int]:
    """
    Return ``(placement_ranks_required, third_place_advancer_count)``.

    * ``placement_ranks_required`` — each group must have ranks ``1`` … ``N`` filled.
    * ``third_place_advancer_count`` — how many third-place teams the user picks
      when ``contestants_advancing`` exceeds ``groups × qualifying_per_group``.
    """
    q = gs.contestants_qualifying_per_group
    n_groups = gs.number_of_groups
    direct = n_groups * q
    advancing = resolve_group_contestants_advancing(gs)
    extra = advancing - direct
    if extra <= 0:
        return q, 0

    # e.g. WC: 2 qualify per group + one 3rd-place finisher per group → pick 8 of 12
    return q + 1, extra


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
