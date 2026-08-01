"""Single-elimination field size and bye math for non-power-of-2 rosters."""

from __future__ import annotations

from typing import Any

STANDARD_KNOCKOUT_STAGE_NAMES: dict[int, str] = {
    64: "Round of 64",
    32: "Round of 32",
    16: "Round of 16",
    8: "Quarterfinals",
    4: "Semifinals",
    2: "Final",
}


def is_power_of_2(n: int) -> bool:
    return n >= 2 and (n & (n - 1)) == 0


def next_power_of_2(n: int) -> int:
    """Smallest power of 2 that is >= n (n >= 1)."""
    if n < 1:
        raise ValueError("n must be at least 1")
    p = 1
    while p < n:
        p *= 2
    return p


def validate_single_elim_roster(roster: int) -> None:
    if roster < 2:
        raise ValueError("Single elimination needs at least 2 teams.")
    if roster % 2 != 0:
        raise ValueError("Single elimination team count must be even.")


def single_elim_field_size(roster: int) -> int:
    """Bracket shell size (next power of 2 >= roster)."""
    validate_single_elim_roster(roster)
    return next_power_of_2(roster)


def single_elim_bye_count(roster: int) -> int:
    """How many teams receive a first-round bye (seeds 1 .. byes)."""
    return single_elim_field_size(roster) - roster


def single_elim_play_in_count(roster: int) -> int:
    """How many teams play in the opening round."""
    return roster - single_elim_bye_count(roster)


def single_elim_bye_draw_pots(roster: int) -> list[dict[str, Any]]:
    """
    Pot layout for random-balanced draws on non-power-of-2 single-elim fields.

    Returns 2–3 pots (empty bands omitted), each with ``label``, ``size``, and
    the bracket ``seeds`` that band maps to after the draw:

    - Bye vs R1 Winners: bye seeds that meet a Round-1 winner next
    - Bye: bye seeds that meet another bye team next
    - Round 1: play-in seeds
    """
    from brackets.utils.bracket_seeding import first_round_seed_pairs

    validate_single_elim_roster(roster)
    if is_power_of_2(roster):
        return []

    field = single_elim_field_size(roster)
    pairs = first_round_seed_pairs(field)

    def _slot_kind(seed_a: int, seed_b: int) -> tuple[str, list[int]]:
        has_a = seed_a <= roster
        has_b = seed_b <= roster
        if has_a and has_b:
            return "PLAY", [seed_a, seed_b]
        if has_a ^ has_b:
            return "BYE", [seed_a if has_a else seed_b]
        return "EMPTY", []

    bye_vs_r1: list[int] = []
    pure_bye: list[int] = []
    round_1: list[int] = []

    # Round-2 game p is fed by Round-1 slots 2p-1 and 2p.
    for p in range(1, field // 4 + 1):
        a1, b1 = pairs[2 * p - 2]
        a2, b2 = pairs[2 * p - 1]
        kind1, seeds1 = _slot_kind(a1, b1)
        kind2, seeds2 = _slot_kind(a2, b2)
        kinds = {kind1, kind2}
        if kinds == {"PLAY", "BYE"}:
            if kind1 == "PLAY":
                round_1.extend(seeds1)
                bye_vs_r1.extend(seeds2)
            else:
                round_1.extend(seeds2)
                bye_vs_r1.extend(seeds1)
        elif kinds == {"BYE"}:
            pure_bye.extend(seeds1)
            pure_bye.extend(seeds2)
        elif kinds == {"PLAY"}:
            round_1.extend(seeds1)
            round_1.extend(seeds2)

    pots: list[dict[str, Any]] = []
    if bye_vs_r1:
        pots.append(
            {
                "key": "bye_vs_r1",
                "label": "Bye vs R1 Winners",
                "size": len(bye_vs_r1),
                "seeds": sorted(bye_vs_r1),
            }
        )
    if pure_bye:
        pots.append(
            {
                "key": "bye",
                "label": "Bye",
                "size": len(pure_bye),
                "seeds": sorted(pure_bye),
            }
        )
    if round_1:
        pots.append(
            {
                "key": "round_1",
                "label": "Round 1",
                "size": len(round_1),
                "seeds": sorted(round_1),
            }
        )
    return pots


def roster_size_from_bracket(bracket) -> int | None:
    """Actual entry count for a single-elim bracket, if known."""
    meta = bracket.metadata if isinstance(bracket.metadata, dict) else {}
    raw = meta.get("roster_size")
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if n >= 2 else None


def knockout_stage_name(
    contestants_entering: int,
    *,
    numbered_early_rounds: bool,
    early_round_number: int = 0,
) -> str:
    """
    Label for a knockout round.

    Power-of-2 fields use Round of N / Quarterfinals / …. Non-power-of-2
    single-elim shells use Round 1, Round 2, … until Quarterfinals.
    """
    if contestants_entering <= 8:
        return STANDARD_KNOCKOUT_STAGE_NAMES.get(
            contestants_entering, f"Round of {contestants_entering}"
        )
    if numbered_early_rounds:
        if early_round_number < 1:
            raise ValueError("early_round_number must be >= 1")
        return f"Round {early_round_number}"
    return STANDARD_KNOCKOUT_STAGE_NAMES.get(
        contestants_entering, f"Round of {contestants_entering}"
    )


def is_default_knockout_stage_name(name: str, contestants_entering: int) -> bool:
    """True when ``name`` looks like an auto-generated knockout label."""
    expected_standard = STANDARD_KNOCKOUT_STAGE_NAMES.get(contestants_entering)
    if name == expected_standard:
        return True
    if name == f"Round of {contestants_entering}":
        return True
    if contestants_entering > 8 and name.startswith("Round "):
        suffix = name[len("Round ") :]
        return suffix.isdigit()
    return False


def sync_single_elim_knockout_stage_names(bracket) -> None:
    """
    Rename auto-generated KO stage labels for non-power-of-2 single-elim
    brackets (Round of 64 → Round 1, …).
    """
    roster = roster_size_from_bracket(bracket)
    if roster is None or is_power_of_2(roster):
        return

    from brackets.models import KnockoutStage

    stages = list(
        KnockoutStage.objects.filter(bracket=bracket, is_third_place=False).order_by(
            "order"
        )
    )
    early = 0
    for ks in stages:
        n = ks.number_of_contestants
        if n > 8:
            early += 1
            expected = knockout_stage_name(
                n, numbered_early_rounds=True, early_round_number=early
            )
        else:
            expected = knockout_stage_name(n, numbered_early_rounds=True)
        if ks.name == expected:
            continue
        if not is_default_knockout_stage_name(ks.name, n):
            continue
        ks.name = expected
        ks.save(update_fields=["name"])
