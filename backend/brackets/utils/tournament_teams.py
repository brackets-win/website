"""Tournament host team roster for single-elim and group+knockout brackets."""

from __future__ import annotations

import re
from typing import Any

from django.db import IntegrityError, transaction

from brackets.models import (
    Bracket,
    BracketContestant,
    BracketStage,
    Contestant,
    Matchup,
    UserBracket,
)
from brackets.utils.contestant_images import resolve_contestant_image_url
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
    from brackets.utils.single_elim_byes import roster_size_from_bracket

    roster = roster_size_from_bracket(bracket)
    team_count = (
        roster
        if roster is not None
        else (first_ko.number_of_contestants if first_ko else 0)
    )
    return {
        "structure": "SINGLE_ELIM",
        "number_of_groups": None,
        "teams_per_group": None,
        "team_count": team_count,
        "field_size": first_ko.number_of_contestants if first_ko else 0,
        "bye_count": (
            (first_ko.number_of_contestants - team_count)
            if first_ko and team_count
            else 0
        ),
    }


def tournament_team_capacity(bracket: Bracket) -> int:
    return int(tournament_structure_meta(bracket)["team_count"] or 0)


def tournament_started(bracket: Bracket) -> bool:
    meta = bracket.metadata if isinstance(bracket.metadata, dict) else {}
    return bool(meta.get("tournament_started"))


def start_tournament(bracket: Bracket) -> None:
    """Lock the roster after setup; Teams tab is no longer shown."""
    required = tournament_team_capacity(bracket)
    if required < 2:
        raise ValueError("This bracket has no team slots configured.")
    if len(tournament_teams_public(bracket)) < required:
        raise ValueError("Add every team before starting the tournament.")
    if tournament_started(bracket):
        return
    meta = dict(bracket.metadata or {})
    meta["tournament_started"] = True
    bracket.metadata = meta
    bracket.save(update_fields=["metadata"])


def tournament_teams_public(bracket: Bracket) -> list[dict[str, Any]]:
    rows = bracket.bracket_contestants.select_related("contestant").order_by(
        "seed", "id"
    )
    out: list[dict[str, Any]] = []
    for bc in rows:
        name = (bc.name_override or "").strip()
        if not name and bc.contestant is not None:
            name = (bc.contestant.name or "").strip()
        if not name:
            continue
        out.append(
            {
                "id": bc.id,
                "name": name,
                "seed": bc.seed,
                "contestant_id": bc.contestant_id,
                "photo_url": (
                    resolve_contestant_image_url(bc.contestant)
                    if bc.contestant is not None
                    else None
                ),
            }
        )
    return out


def tournament_teams_response(bracket: Bracket) -> dict[str, Any]:
    meta = tournament_structure_meta(bracket)
    return {
        **meta,
        "teams": tournament_teams_public(bracket),
        "tournament_started": tournament_started(bracket),
    }


def unique_contestant_identifier(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip().lower()).strip("-")
    if not base:
        base = "team"
    base = base[:50]
    candidate = base
    n = 2
    while Contestant.objects.filter(identifier=candidate).exists():
        suffix = f"-{n}"
        candidate = f"{base[: 64 - len(suffix)]}{suffix}"
        n += 1
    return candidate


def create_tournament_contestant(
    *,
    user,
    name: str,
    photo=None,
    image_url: str = "",
    description: str = "",
) -> Contestant:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    if len(name) > 100:
        raise ValueError("Team names must be 100 characters or fewer.")
    image_url = (image_url or "").strip()
    description = (description or "").strip()
    for _ in range(8):
        identifier = unique_contestant_identifier(name)
        try:
            return Contestant.objects.create(
                identifier=identifier,
                name=name,
                description=description,
                created_by=user,
                photo=photo if photo else None,
                image_url=image_url,
            )
        except IntegrityError:
            continue
    raise ValueError("Could not allocate a unique team identifier.")


def is_structural_bye_matchup(matchup) -> bool:
    """
    True for single-elim bye slots: exactly one side filled, winner is that team.

    These are auto-created when the roster is smaller than the bracket shell and
    must not count as recorded results (they block redraw / start otherwise).
    """
    c1 = matchup.contestant1_id
    c2 = matchup.contestant2_id
    w = matchup.winner_id
    if c1 is not None and c2 is None:
        return w is None or w == c1
    if c2 is not None and c1 is None:
        return w is None or w == c2
    return False


def _assert_roster_editable(bracket: Bracket, master: UserBracket) -> None:
    if tournament_started(bracket):
        raise ValueError(
            "Teams are locked after the tournament has started."
        )
    for m in master.matchup_set.filter(winner_id__isnull=False).iterator():
        if not is_structural_bye_matchup(m):
            raise ValueError(
                "Cannot change teams after results have been recorded. "
                "Clear winners on the bracket first."
            )
    gp = (master.metadata or {}).get("group_positions") or {}
    if isinstance(gp, dict) and any(
        isinstance(v, dict) and any(x is not None for x in v.values())
        for v in gp.values()
    ):
        raise ValueError(
            "Cannot change teams after group standings have been recorded. "
            "Clear group positions first."
        )


@transaction.atomic
def apply_tournament_teams(
    bracket: Bracket,
    teams: list[dict[str, Any]],
    *,
    created_by=None,
) -> list[dict[str, Any]]:
    """
    Replace the bracket roster and rebuild the master bracket tree.

    Each team may include ``contestant_id`` (preferred) and/or ``name``.
    Name-only rows create a ``Contestant`` when ``created_by`` is provided.
    """
    required = tournament_team_capacity(bracket)
    if required < 2:
        raise ValueError("This bracket has no team slots configured.")

    if len(teams) != required:
        raise ValueError(f"Provide exactly {required} teams.")

    master: UserBracket = bracket.get_master_bracket()
    _assert_roster_editable(bracket, master)

    parsed: list[tuple[Contestant | None, str, int | None]] = []
    seen_contestants: set[int] = set()
    for row in teams:
        if not isinstance(row, dict):
            raise ValueError("Each team must be an object with a name.")
        cid_raw = row.get("contestant_id")
        contestant: Contestant | None = None
        if cid_raw is not None and str(cid_raw).strip() != "":
            try:
                cid = int(cid_raw)
            except (TypeError, ValueError) as e:
                raise ValueError("contestant_id must be a number.") from e
            contestant = Contestant.objects.filter(pk=cid).first()
            if contestant is None:
                raise ValueError(f"Unknown contestant {cid}.")
            if cid in seen_contestants:
                raise ValueError("Each team can only be used once.")
            seen_contestants.add(cid)

        name = str(row.get("name") or "").strip()
        if contestant is not None:
            name = (contestant.name or "").strip() or name
        if not name:
            raise ValueError("Each team needs a name.")
        if len(name) > 100:
            raise ValueError("Team names must be 100 characters or fewer.")

        if contestant is None and created_by is not None:
            contestant = create_tournament_contestant(
                user=created_by, name=name
            )
            if contestant.id in seen_contestants:
                raise ValueError("Each team can only be used once.")
            seen_contestants.add(contestant.id)

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
        parsed.append((contestant, name, seed))

    bracket.bracket_contestants.all().delete()
    for idx, (contestant, name, seed) in enumerate(parsed):
        BracketContestant.objects.create(
            bracket=bracket,
            contestant=contestant,
            name_override="" if contestant is not None else name,
            seed=seed if seed is not None else idx + 1,
        )

    Matchup.objects.filter(user_bracket=master).delete()
    if master.metadata:
        meta = dict(master.metadata)
        meta.pop("group_positions", None)
        meta.pop("third_place_advancers", None)
        master.metadata = meta or None
        master.save(update_fields=["metadata"])

    ensure_knockout_structure_for_user_bracket(master)
    return tournament_teams_public(bracket)


def link_name_only_tournament_teams(bracket: Bracket, user) -> bool:
    """Upgrade legacy name_override-only roster rows to Contestant FKs."""
    changed = False
    for bc in bracket.bracket_contestants.filter(contestant__isnull=True):
        name = (bc.name_override or "").strip()
        if not name:
            continue
        contestant = create_tournament_contestant(user=user, name=name)
        bc.contestant = contestant
        bc.name_override = ""
        bc.save(update_fields=["contestant", "name_override"])
        changed = True
    return changed


@transaction.atomic
def draw_and_apply_tournament_teams(
    bracket: Bracket,
    *,
    mode: str,
    teams: list[dict[str, Any]],
    created_by=None,
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
    return apply_tournament_teams(bracket, seeded, created_by=created_by)
