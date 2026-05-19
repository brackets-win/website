"""Read group-stage advancement rules from the bracket's linked GroupStage row."""

from __future__ import annotations

from brackets.models import Bracket, BracketStage, GroupStage


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
    advancing = gs.contestants_advancing
    if advancing is None:
        return q, 0

    direct = n_groups * q
    extra = advancing - direct
    if extra <= 0:
        return q, 0

    # e.g. WC: 2 qualify per group + one 3rd-place finisher per group → pick 8 of 12
    return q + 1, extra
