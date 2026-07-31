"""Tournament host team roster for single-elim and group+knockout brackets."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from brackets.models import Bracket, BracketContestant, BracketStage, Matchup, UserBracket
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket


def tournament_structure_meta(bracket: Bracket) -> dict[str, Any]:
    group_stage = (
        bracket.stages.filter(stage_type=BracketStage.StageType.GROUP)
        .order_by("order")
        .first()
    )
    if group_stage is not None:
        from brackets.models import GroupStage

        gs = GroupStage.objects.filter(pk=group_stage.pk).first()
        num_groups = gs.number_of_groups if gs else None
        teams_per_group = None
        if num_groups and num_groups > 0 and group_stage.number_of_contestants:
            teams_per_group = group_stage.number_of_contestants // num_groups
        return {
            "structure": "GROUP_KNOCKOUT",
            "number_of_groups": num_groups,
            "teams_per_group": teams_per_group,
            "team_count": group_stage.number_of_contestants,
        }

    first_ko = (
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT)
        .order_by("order")
        .first()
    )
    return {
        "structure": "SINGLE_ELIM",
        "number_of_groups": None,
        "teams_per_group": None,
        "team_count": first_ko.number_of_contestants if first_ko else 0,
    }


def tournament_team_capacity(bracket: Bracket) -> int:
    return int(tournament_structure_meta(bracket)["team_count"] or 0)


def tournament_teams_public(bracket: Bracket) -> list[dict[str, Any]]:
    rows = list(
        bracket.bracket_contestants.order_by("seed", "id").values(
            "id", "name_override", "seed"
        )
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        name = (row["name_override"] or "").strip()
        if not name:
            continue
        out.append(
            {
                "id": row["id"],
                "name": name,
                "seed": row["seed"],
            }
        )
    return out


def tournament_teams_response(bracket: Bracket) -> dict[str, Any]:
    meta = tournament_structure_meta(bracket)
    return {
        **meta,
        "teams": tournament_teams_public(bracket),
    }


@transaction.atomic
def apply_tournament_teams(bracket: Bracket, teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Replace the bracket roster with ad-hoc team names and rebuild the master bracket tree.
    """
    required = tournament_team_capacity(bracket)
    if required < 2:
        raise ValueError("This bracket has no team slots configured.")

    if len(teams) != required:
        raise ValueError(f"Provide exactly {required} teams.")

    master: UserBracket = bracket.get_master_bracket()
    if master.matchup_set.filter(winner_id__isnull=False).exists():
        raise ValueError(
            "Cannot change teams after results have been recorded. "
            "Clear winners on the bracket first."
        )
    # Group standings also count as results for GK tournaments.
    gp = (master.metadata or {}).get("group_positions") or {}
    if isinstance(gp, dict) and any(
        isinstance(v, dict) and any(x is not None for x in v.values())
        for v in gp.values()
    ):
        raise ValueError(
            "Cannot change teams after group standings have been recorded. "
            "Clear group positions first."
        )

    parsed: list[tuple[str, int | None]] = []
    for row in teams:
        if not isinstance(row, dict):
            raise ValueError("Each team must be an object with a name.")
        name = str(row.get("name") or "").strip()
        if not name:
            raise ValueError("Each team needs a name.")
        if len(name) > 100:
            raise ValueError("Team names must be 100 characters or fewer.")
        seed_raw = row.get("seed")
        seed: int | None
        if seed_raw is None or str(seed_raw).strip() == "":
            seed = None
        else:
            try:
                seed = int(seed_raw)
            except (TypeError, ValueError) as e:
                raise ValueError("Seed must be a number.") from e
            if seed < 1:
                raise ValueError("Seed must be at least 1.")
        parsed.append((name, seed))

    bracket.bracket_contestants.all().delete()
    for idx, (name, seed) in enumerate(parsed):
        BracketContestant.objects.create(
            bracket=bracket,
            name_override=name,
            seed=seed if seed is not None else idx + 1,
        )

    Matchup.objects.filter(user_bracket=master).delete()
    # Clear stale group standings when rebuilding roster.
    if master.metadata:
        meta = dict(master.metadata)
        meta.pop("group_positions", None)
        meta.pop("third_place_advancers", None)
        master.metadata = meta or None
        master.save(update_fields=["metadata"])

    ensure_knockout_structure_for_user_bracket(master)
    return tournament_teams_public(bracket)


@transaction.atomic
def draw_and_apply_tournament_teams(
    bracket: Bracket,
    *,
    mode: str,
    teams: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from brackets.utils.tournament_placement import compute_draw_seeds

    meta = tournament_structure_meta(bracket)
    seeded = compute_draw_seeds(
        mode=mode,
        teams=teams,
        structure=meta["structure"],
        number_of_groups=meta["number_of_groups"],
        teams_per_group=meta["teams_per_group"],
    )
    return apply_tournament_teams(bracket, seeded)
