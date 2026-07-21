"""
Per-knockout-stage seeding: standard tree, reseed (1 vs N), or randomize.

Standard advancement still uses Matchup.get_next_matchup position math.
Reseed / randomize fill a destination stage only once every matchup in the
previous main knockout round has a winner.
"""

from __future__ import annotations

import hashlib
import random
from typing import Iterable, Sequence

from django.db import transaction

from brackets.models import BracketStage, KnockoutStage, Matchup, UserBracket

STANDARD = KnockoutStage.SeedingMode.STANDARD
RESEED = KnockoutStage.SeedingMode.RESEED
RANDOMIZE = KnockoutStage.SeedingMode.RANDOMIZE

VALID_SEEDING_MODES = frozenset({STANDARD, RESEED, RANDOMIZE})


def normalize_seeding_mode(raw) -> str:
    if raw is None:
        return STANDARD
    value = str(raw).strip().lower()
    if value in VALID_SEEDING_MODES:
        return value
    return STANDARD


def seeding_mode_for_stage(stage) -> str:
    """Resolve seeding mode for a knockout stage (defaults to standard)."""
    if stage is None:
        return STANDARD
    try:
        ks = (
            stage
            if isinstance(stage, KnockoutStage)
            else KnockoutStage.objects.get(pk=stage.pk)
        )
    except KnockoutStage.DoesNotExist:
        return STANDARD
    if ks.is_third_place:
        return STANDARD
    return normalize_seeding_mode(ks.seeding_mode)


def is_dynamic_seeding_mode(mode: str) -> bool:
    return normalize_seeding_mode(mode) in (RESEED, RANDOMIZE)


def previous_main_knockout_stage(bracket, stage: BracketStage) -> BracketStage | None:
    """Nearest earlier main (non–third-place) knockout stage."""
    candidates = bracket.stages.filter(
        stage_type=BracketStage.StageType.KNOCKOUT,
        order__lt=stage.order,
    ).order_by("-order")
    for candidate in candidates:
        try:
            ks = KnockoutStage.objects.get(pk=candidate.pk)
        except KnockoutStage.DoesNotExist:
            continue
        if not ks.is_third_place:
            return candidate
    return None


def next_main_knockout_stage(bracket, stage: BracketStage) -> BracketStage | None:
    """Nearest later main (non–third-place) knockout stage."""
    candidates = bracket.stages.filter(
        stage_type=BracketStage.StageType.KNOCKOUT,
        order__gt=stage.order,
    ).order_by("order")
    for candidate in candidates:
        try:
            ks = KnockoutStage.objects.get(pk=candidate.pk)
        except KnockoutStage.DoesNotExist:
            continue
        if not ks.is_third_place:
            return candidate
    return None


def pair_reseed(contestants_best_first: Sequence) -> list[tuple]:
    """Highest seed vs lowest, second-highest vs second-lowest, …"""
    n = len(contestants_best_first)
    if n < 2 or n % 2:
        raise ValueError("reseed requires an even number of contestants (at least 2)")
    pairs: list[tuple] = []
    for i in range(n // 2):
        pairs.append((contestants_best_first[i], contestants_best_first[n - 1 - i]))
    return pairs


def pair_randomize(contestants: Sequence, *, rng: random.Random) -> list[tuple]:
    """Shuffle then pair adjacent slots (1v2, 3v4, …)."""
    n = len(contestants)
    if n < 2 or n % 2:
        raise ValueError("randomize requires an even number of contestants (at least 2)")
    shuffled = list(contestants)
    rng.shuffle(shuffled)
    return [(shuffled[i], shuffled[i + 1]) for i in range(0, n, 2)]


def rng_for_stage_draw(
    user_bracket_id: int,
    stage_id: int,
    winner_ids: Iterable[int],
) -> random.Random:
    """Deterministic RNG so the same winners always draw the same matchups."""
    payload = (
        f"{user_bracket_id}:{stage_id}:"
        f"{','.join(str(i) for i in sorted(winner_ids))}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def sort_contestants_by_seed(contestants: Sequence) -> list:
    return sorted(
        contestants,
        key=lambda c: (
            c.seed if getattr(c, "seed", None) is not None else float("inf"),
            c.id,
        ),
    )


def first_round_pairs_for_mode(contestants: Sequence, mode: str, *, rng: random.Random):
    """
    Initial single-elim first-round pairs for a seeding mode.

    ``contestants`` must already be ordered by seed ascending (seed 1 first).
    """
    mode = normalize_seeding_mode(mode)
    n = len(contestants)
    if mode == STANDARD:
        from brackets.utils.bracket_seeding import first_round_seed_pairs

        pairs = []
        for seed1, seed2 in first_round_seed_pairs(n):
            pairs.append((contestants[seed1 - 1], contestants[seed2 - 1]))
        return pairs
    if mode == RESEED:
        return pair_reseed(sort_contestants_by_seed(contestants))
    return pair_randomize(list(contestants), rng=rng)


def _clear_matchups(matchups: list[Matchup]) -> None:
    for m in matchups:
        if m.contestant1_id is None and m.contestant2_id is None and m.winner_id is None:
            continue
        m.contestant1 = None
        m.contestant2 = None
        m.winner = None
        m.save(update_fields=["contestant1", "contestant2", "winner"])


@transaction.atomic
def clear_knockout_from_stage(user_bracket: UserBracket, from_stage: BracketStage) -> None:
    """Clear contestants/winners on ``from_stage`` and all later knockout stages."""
    later = list(
        user_bracket.bracket.stages.filter(
            stage_type=BracketStage.StageType.KNOCKOUT,
            order__gte=from_stage.order,
        ).order_by("order")
    )
    for stage in later:
        matchups = list(
            Matchup.objects.filter(user_bracket=user_bracket, stage=stage).order_by(
                "position"
            )
        )
        _clear_matchups(matchups)


@transaction.atomic
def sync_knockout_stage_seeding(
    user_bracket: UserBracket,
    dest_stage: BracketStage,
) -> None:
    """
    Fill or clear ``dest_stage`` according to its seeding mode and previous winners.

    No-op for standard mode and third-place stages. For reseed/randomize, clears the
    destination (and later rounds) when the previous round is incomplete.
    """
    mode = seeding_mode_for_stage(dest_stage)
    if not is_dynamic_seeding_mode(mode):
        return

    prev = previous_main_knockout_stage(user_bracket.bracket, dest_stage)
    if prev is None:
        return

    prev_matchups = list(
        Matchup.objects.filter(user_bracket=user_bracket, stage=prev)
        .select_related("winner")
        .order_by("position")
    )
    if not prev_matchups or any(m.winner_id is None for m in prev_matchups):
        clear_knockout_from_stage(user_bracket, dest_stage)
        return

    winners = [m.winner for m in prev_matchups if m.winner is not None]
    if mode == RESEED:
        pairs = pair_reseed(sort_contestants_by_seed(winners))
    else:
        rng = rng_for_stage_draw(
            user_bracket.id,
            dest_stage.id,
            [w.id for w in winners],
        )
        pairs = pair_randomize(winners, rng=rng)

    matchups = list(
        Matchup.objects.filter(user_bracket=user_bracket, stage=dest_stage).order_by(
            "position"
        )
    )
    if len(matchups) != len(pairs):
        raise ValueError(
            f"Stage {dest_stage.name} has {len(matchups)} matchups but "
            f"{len(pairs)} pairs to assign"
        )

    pairs_changed = False
    for m, (c1, c2) in zip(matchups, pairs):
        if m.contestant1_id != c1.id or m.contestant2_id != c2.id:
            pairs_changed = True
            break

    if pairs_changed:
        # Final, third place, and any later main rounds sit at order > dest.
        later = (
            user_bracket.bracket.stages.filter(
                stage_type=BracketStage.StageType.KNOCKOUT,
                order__gt=dest_stage.order,
            )
            .order_by("order")
            .first()
        )
        if later is not None:
            clear_knockout_from_stage(user_bracket, later)

    for m, (c1, c2) in zip(matchups, pairs):
        new_ids = {c1.id, c2.id}
        fields = ["contestant1", "contestant2"]
        m.contestant1 = c1
        m.contestant2 = c2
        if m.winner_id and m.winner_id not in new_ids:
            m.winner = None
            fields.append("winner")
        m.save(update_fields=fields)


def propagate_to_next_stage(matchup: Matchup) -> None:
    """
    Advance ``matchup``'s winner into the next main knockout stage.

    Standard: place into the tree slot. Reseed/randomize: sync the whole next stage.
    """
    dest = next_main_knockout_stage(matchup.user_bracket.bracket, matchup.stage)
    if dest is None:
        return

    mode = seeding_mode_for_stage(dest)
    if is_dynamic_seeding_mode(mode):
        sync_knockout_stage_seeding(matchup.user_bracket, dest)
        return

    # Standard tree placement (same math as Matchup.get_next_matchup).
    next_matchup = matchup.get_next_matchup()
    if not next_matchup or not matchup.winner_id:
        return

    from brackets.utils.knockout_rebuild import remove_team_from_knockout_path

    if matchup.is_team_a():
        old_id = next_matchup.contestant1_id
        if old_id and old_id != matchup.winner_id:
            remove_team_from_knockout_path(matchup, old_id)
            next_matchup.refresh_from_db(
                fields=["contestant1", "contestant2", "winner"]
            )
        next_matchup.contestant1 = matchup.winner
    else:
        old_id = next_matchup.contestant2_id
        if old_id and old_id != matchup.winner_id:
            remove_team_from_knockout_path(matchup, old_id)
            next_matchup.refresh_from_db(
                fields=["contestant1", "contestant2", "winner"]
            )
        next_matchup.contestant2 = matchup.winner
    next_matchup.save(update_fields=["contestant1", "contestant2"])
