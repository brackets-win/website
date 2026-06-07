"""Tournament host team roster for single-elim brackets."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from brackets.models import Bracket, BracketContestant, BracketStage, Matchup, UserBracket
from brackets.utils.knockout_tree import ensure_knockout_structure_for_user_bracket


def tournament_team_capacity(bracket: Bracket) -> int:
    first_ko = (
        bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT)
        .order_by("order")
        .first()
    )
    if first_ko is None:
        return 0
    return first_ko.number_of_contestants


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


@transaction.atomic
def apply_tournament_teams(bracket: Bracket, teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Replace the bracket roster with ad-hoc team names and rebuild the master bracket tree.
    """
    required = tournament_team_capacity(bracket)
    if required < 2:
        raise ValueError("This bracket has no knockout stage.")

    if len(teams) != required:
        raise ValueError(f"Provide exactly {required} teams.")

    master: UserBracket = bracket.get_master_bracket()
    if master.matchup_set.filter(winner_id__isnull=False).exists():
        raise ValueError(
            "Cannot change teams after results have been recorded. "
            "Clear winners on the bracket first."
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
    ensure_knockout_structure_for_user_bracket(master)
    return tournament_teams_public(bracket)
