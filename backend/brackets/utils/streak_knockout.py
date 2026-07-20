"""H2H knockout bracket for streak challenges."""

from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from brackets.models import (
    StreakChallenge,
    StreakKnockout,
    StreakKnockoutMatch,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
)
from brackets.utils.streak_knockout_rules import (
    headstart_for_round,
    knockout_round_label,
    knockout_total_rounds,
    knockout_third_place_supported,
    round_start_at,
    semi_final_round_index,
    third_place_match_enabled,
)
from brackets.utils.bracket_seeding import first_round_seed_pairs
from brackets.utils.leaderboard_preview import streak_participant_label, streak_ranked_participants
from brackets.utils.streak_scoring import _is_correct


def bracket_qualifier_count(participant_count: int) -> int:
    if participant_count < 2:
        return participant_count
    return 2 ** int(math.floor(math.log2(participant_count)))


def _participant_by_seed(
    seeded: list[tuple[StreakParticipant, int]],
) -> dict[int, StreakParticipant]:
    return {seed: p for p, seed in seeded}


def _matches_in_round(bracket_size: int, round_index: int) -> int:
    if round_index <= 0:
        return 0
    return max(1, bracket_size // (2**round_index))


def _seed_participants(
    participants: list[StreakParticipant],
) -> list[tuple[StreakParticipant, int]]:
    answered = [p for p in participants if p.wins + p.losses > 0]
    if answered:
        ranked = streak_ranked_participants(participants)
        return [(p, idx) for idx, (p, _rank) in enumerate(ranked, start=1)]

    shuffled = list(participants)
    random.shuffle(shuffled)
    return [(p, i + 1) for i, p in enumerate(shuffled)]


def _freeze_participant_stats(p: StreakParticipant) -> None:
    p.frozen_best_win_streak = p.best_win_streak
    p.frozen_wins = p.wins
    p.frozen_losses = p.losses
    p.frozen_streak_signed = p.streak_signed
    p.frozen_best_loss_streak = p.best_loss_streak


def _correct_picks_in_window(
    challenge_id: int,
    user_id: int,
    window_start: datetime,
    window_end: datetime,
) -> int:
    picks = StreakPick.objects.filter(
        streak_challenge_id=challenge_id,
        user_id=user_id,
        question__resolved_at__isnull=False,
        question__correct_choice_id__isnull=False,
        question__closes_at__gte=window_start,
        question__closes_at__lt=window_end,
    ).select_related("question")
    return sum(1 for pick in picks if _is_correct(pick, pick.question))


def _match_score(
    participant: StreakParticipant | None,
    *,
    challenge_id: int,
    window_start: datetime,
    window_end: datetime,
    headstart_enabled: bool,
) -> int:
    if participant is None:
        return 0
    headstart = participant.frozen_best_win_streak if headstart_enabled else 0
    correct = _correct_picks_in_window(
        challenge_id,
        participant.user_id,
        window_start,
        window_end,
    )
    return headstart + correct


def _score_breakdown_from_total(
    participant: StreakParticipant | None,
    total_score: int,
    *,
    bonus_enabled: bool,
) -> tuple[int, int]:
    if participant is None:
        return 0, 0
    bonus = participant.frozen_best_win_streak if bonus_enabled else 0
    correct = max(0, total_score - bonus)
    return correct, bonus


def _pick_winner(
    match: StreakKnockoutMatch,
    score_a: int,
    score_b: int,
) -> StreakParticipant | None:
    if match.player_a is None and match.player_b is None:
        return None
    if match.player_a is None:
        return match.player_b
    if match.player_b is None:
        return match.player_a
    if score_a > score_b:
        return match.player_a
    if score_b > score_a:
        return match.player_b
    if match.seed_a <= match.seed_b:
        return match.player_a
    return match.player_b


def _unresolved_in_window(
    competition_id: int,
    window_start: datetime,
    window_end: datetime,
) -> int:
    return StreakQuestion.objects.filter(
        streak_competition_id=competition_id,
        closes_at__gte=window_start,
        closes_at__lt=window_end,
        resolved_at__isnull=True,
    ).count()


@transaction.atomic
def start_knockout(challenge: StreakChallenge) -> StreakKnockout:
    if challenge.mode == StreakChallenge.Mode.KNOCKOUT:
        raise ValueError("Challenge is already in knockout mode")
    if challenge.streak_competition.ended_at is not None:
        raise ValueError("Competition has ended")

    participants = list(
        StreakParticipant.objects.filter(streak_challenge=challenge).select_related(
            "user"
        )
    )
    if len(participants) < 2:
        raise ValueError("At least two participants are required")

    now = timezone.now()

    for p in participants:
        _freeze_participant_stats(p)
        p.in_knockout_bracket = False
        p.knockout_seed = None
        p.bracket_eliminated_at = None
        p.consolation_wins = 0
        p.consolation_losses = 0
        p.consolation_eligible_from = now
        p.save(
            update_fields=[
                "frozen_best_win_streak",
                "frozen_wins",
                "frozen_losses",
                "frozen_streak_signed",
                "frozen_best_loss_streak",
                "in_knockout_bracket",
                "knockout_seed",
                "bracket_eliminated_at",
                "consolation_wins",
                "consolation_losses",
                "consolation_eligible_from",
            ]
        )

    seeded = _seed_participants(participants)
    bracket_size = bracket_qualifier_count(len(seeded))
    qualifiers = seeded[:bracket_size]
    by_seed = _participant_by_seed(qualifiers)

    challenge.mode = StreakChallenge.Mode.KNOCKOUT
    challenge.save(update_fields=["mode"])

    for p, seed in qualifiers:
        p.in_knockout_bracket = True
        p.knockout_seed = seed
        p.consolation_eligible_from = None
        p.save(update_fields=["in_knockout_bracket", "knockout_seed", "consolation_eligible_from"])

    knockout = StreakKnockout.objects.create(
        streak_challenge=challenge,
        status=StreakKnockout.Status.SETUP,
        current_round=0,
        headstart_enabled=True,
    )

    pairs = first_round_seed_pairs(bracket_size)
    for position, (seed_a, seed_b) in enumerate(pairs, start=1):
        StreakKnockoutMatch.objects.create(
            knockout=knockout,
            round_index=1,
            position=position,
            player_a=by_seed.get(seed_a),
            player_b=by_seed.get(seed_b),
            seed_a=seed_a,
            seed_b=seed_b,
        )

    return knockout


@transaction.atomic
def swap_round1_players(
    knockout: StreakKnockout,
    *,
    match_position: int,
    slot: str,
    participant_id: int,
) -> None:
    if knockout.status != StreakKnockout.Status.SETUP:
        raise ValueError("Bracket setup is locked")
    if slot not in ("a", "b"):
        raise ValueError("slot must be 'a' or 'b'")

    match = knockout.matches.filter(round_index=1, position=match_position).first()
    if match is None:
        raise ValueError("Match not found")

    participant = StreakParticipant.objects.filter(
        pk=participant_id,
        streak_challenge=knockout.streak_challenge,
    ).first()
    if participant is None:
        raise ValueError("Participant not found")

    displaced = match.player_a if slot == "a" else match.player_b
    if displaced is not None and displaced.id != participant.id:
        displaced.in_knockout_bracket = False
        displaced.knockout_seed = None
        displaced.consolation_eligible_from = timezone.now()
        displaced.save(
            update_fields=[
                "in_knockout_bracket",
                "knockout_seed",
                "consolation_eligible_from",
            ]
        )

    if participant.in_knockout_bracket and participant.id != (displaced.id if displaced else None):
        other = knockout.matches.filter(round_index=1).exclude(pk=match.pk)
        for m in other:
            if m.player_a_id == participant.id:
                m.player_a = None
                m.seed_a = 0
                m.save(update_fields=["player_a", "seed_a"])
            if m.player_b_id == participant.id:
                m.player_b = None
                m.seed_b = 0
                m.save(update_fields=["player_b", "seed_b"])

    if slot == "a":
        if participant.in_knockout_bracket:
            match.seed_a = participant.knockout_seed or 0
        else:
            participant.in_knockout_bracket = True
            participant.knockout_seed = match.seed_a or 99
            participant.consolation_eligible_from = None
            participant.save(
                update_fields=[
                    "in_knockout_bracket",
                    "knockout_seed",
                    "consolation_eligible_from",
                ]
            )
        match.player_a = participant
        match.save(update_fields=["player_a", "seed_a"])
    else:
        if participant.in_knockout_bracket:
            match.seed_b = participant.knockout_seed or 0
        else:
            participant.in_knockout_bracket = True
            participant.knockout_seed = match.seed_b or 99
            participant.consolation_eligible_from = None
            participant.save(
                update_fields=[
                    "in_knockout_bracket",
                    "knockout_seed",
                    "consolation_eligible_from",
                ]
            )
        match.player_b = participant
        match.save(update_fields=["player_b", "seed_b"])


def _eliminate_to_consolation(player: StreakParticipant, when: datetime) -> None:
    player.bracket_eliminated_at = when
    player.consolation_eligible_from = when
    player.in_knockout_bracket = False
    player.save(
        update_fields=[
            "bracket_eliminated_at",
            "consolation_eligible_from",
            "in_knockout_bracket",
        ]
    )


def _eliminate_from_bracket_no_consolation(
    player: StreakParticipant, when: datetime
) -> None:
    player.bracket_eliminated_at = when
    player.in_knockout_bracket = False
    player.save(update_fields=["bracket_eliminated_at", "in_knockout_bracket"])


def _create_third_place_match(
    knockout: StreakKnockout,
    *,
    loser_a: StreakParticipant,
    loser_b: StreakParticipant,
    source_a: StreakKnockoutMatch,
    source_b: StreakKnockoutMatch,
    total_rounds: int,
) -> StreakKnockoutMatch:
    existing = knockout.matches.filter(is_third_place=True).first()
    if existing is not None:
        return existing
    return StreakKnockoutMatch.objects.create(
        knockout=knockout,
        round_index=total_rounds,
        position=2,
        is_third_place=True,
        player_a=loser_a,
        player_b=loser_b,
        seed_a=loser_a.knockout_seed or 0,
        seed_b=loser_b.knockout_seed or 0,
        source_match_a=source_a,
        source_match_b=source_b,
    )


def _score_match(
    knockout: StreakKnockout,
    match: StreakKnockoutMatch,
    *,
    window_start: datetime,
    window_end: datetime,
    headstart_enabled: bool,
) -> None:
    score_a = _match_score(
        match.player_a,
        challenge_id=knockout.streak_challenge_id,
        window_start=window_start,
        window_end=window_end,
        headstart_enabled=headstart_enabled,
    )
    score_b = _match_score(
        match.player_b,
        challenge_id=knockout.streak_challenge_id,
        window_start=window_start,
        window_end=window_end,
        headstart_enabled=headstart_enabled,
    )
    winner = _pick_winner(match, score_a, score_b)
    match.score_a = score_a
    match.score_b = score_b
    match.winner = winner
    match.finalized = True
    match.save(update_fields=["score_a", "score_b", "winner", "finalized"])


def _finalize_round(
    knockout: StreakKnockout,
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[StreakKnockoutMatch]:
    challenge = knockout.streak_challenge
    participant_count = challenge.participants.count()
    total_rounds = knockout_total_rounds(participant_count)
    third_place_on = third_place_match_enabled(challenge, participant_count)
    semi_round = semi_final_round_index(total_rounds)
    is_semi_round = (
        semi_round is not None and knockout.current_round == semi_round
    )
    headstart_enabled = headstart_for_round(challenge, knockout.current_round)

    matches = list(
        knockout.matches.filter(
            round_index=knockout.current_round,
            finalized=False,
            is_third_place=False,
        ).select_related("player_a", "player_b")
    )
    now = window_end
    semi_losers: list[tuple[StreakParticipant, StreakKnockoutMatch]] = []

    for match in matches:
        _score_match(
            knockout,
            match,
            window_start=window_start,
            window_end=window_end,
            headstart_enabled=headstart_enabled,
        )
        winner = match.winner
        for player in (match.player_a, match.player_b):
            if player is None or winner is None:
                continue
            if player.id == winner.id:
                continue
            if is_semi_round and third_place_on:
                semi_losers.append((player, match))
            else:
                _eliminate_to_consolation(player, now)

    if is_semi_round and third_place_on and len(semi_losers) == 2:
        _create_third_place_match(
            knockout,
            loser_a=semi_losers[0][0],
            loser_b=semi_losers[1][0],
            source_a=semi_losers[0][1],
            source_b=semi_losers[1][1],
            total_rounds=total_rounds,
        )

    return matches


def _finalize_third_place_match(
    knockout: StreakKnockout,
    *,
    window_start: datetime,
    window_end: datetime,
) -> StreakKnockoutMatch | None:
    match = knockout.matches.filter(is_third_place=True, finalized=False).first()
    if match is None:
        return None
    challenge = knockout.streak_challenge
    headstart_enabled = headstart_for_round(challenge, match.round_index)
    _score_match(
        knockout,
        match,
        window_start=window_start,
        window_end=window_end,
        headstart_enabled=headstart_enabled,
    )
    now = window_end
    for player in (match.player_a, match.player_b):
        if player is not None:
            _eliminate_from_bracket_no_consolation(player, now)
    return match


def _build_next_round(
    knockout: StreakKnockout,
    finalized_matches: list[StreakKnockoutMatch],
) -> list[StreakKnockoutMatch]:
    winners = [m.winner for m in finalized_matches if m.winner is not None]
    if len(winners) <= 1:
        return []

    next_round = knockout.current_round + 1
    created: list[StreakKnockoutMatch] = []
    for i in range(0, len(finalized_matches), 2):
        source_a = finalized_matches[i]
        source_b = finalized_matches[i + 1] if i + 1 < len(finalized_matches) else None
        match = StreakKnockoutMatch.objects.create(
            knockout=knockout,
            round_index=next_round,
            position=(i // 2) + 1,
            source_match_a=source_a,
            source_match_b=source_b,
        )
        if source_a.winner:
            match.player_a = source_a.winner
            match.seed_a = source_a.winner.knockout_seed or 0
        if source_b and source_b.winner:
            match.player_b = source_b.winner
            match.seed_b = source_b.winner.knockout_seed or 0
        match.save(update_fields=["player_a", "player_b", "seed_a", "seed_b"])
        created.append(match)
    return created


@transaction.atomic
def advance_knockout_round(
    knockout: StreakKnockout,
    *,
    headstart_enabled: bool,
) -> dict[str, Any]:
    if knockout.status == StreakKnockout.Status.COMPLETE:
        raise ValueError("Knockout is complete")

    now = timezone.now()
    challenge = knockout.streak_challenge
    warnings: list[str] = []

    if knockout.status == StreakKnockout.Status.SETUP:
        round_start = round_start_at(challenge, 1) or now
        knockout.status = StreakKnockout.Status.IN_PROGRESS
        knockout.current_round = 1
        knockout.round_started_at = round_start
        knockout.headstart_enabled = headstart_enabled
        knockout.save(
            update_fields=[
                "status",
                "current_round",
                "round_started_at",
                "headstart_enabled",
            ]
        )
        return {"warnings": warnings, "completed": False}

    if knockout.round_started_at is None:
        raise ValueError("Round has not started")

    unresolved = _unresolved_in_window(
        challenge.streak_competition_id,
        knockout.round_started_at,
        now,
    )
    if unresolved:
        warnings.append(
            f"{unresolved} question{'s' if unresolved != 1 else ''} in this round "
            "are not resolved yet and will not count."
        )

    next_round_index = knockout.current_round + 1
    scheduled_end = round_start_at(challenge, next_round_index)
    if scheduled_end is not None:
        if timezone.is_naive(scheduled_end):
            scheduled_end = timezone.make_aware(scheduled_end)
        if scheduled_end <= now:
            window_end = scheduled_end
        else:
            window_end = now
    else:
        window_end = now

    finalized = _finalize_round(
        knockout,
        window_start=knockout.round_started_at,
        window_end=window_end,
    )

    participant_count = challenge.participants.count()
    total_rounds = knockout_total_rounds(participant_count)
    if knockout.current_round == total_rounds:
        _finalize_third_place_match(
            knockout,
            window_start=knockout.round_started_at,
            window_end=window_end,
        )

    winners = [m.winner for m in finalized if m.winner is not None]
    if len(winners) == 1:
        knockout.status = StreakKnockout.Status.COMPLETE
        knockout.champion = winners[0]
        knockout.completed_at = now
        knockout.round_started_at = None
        knockout.save(
            update_fields=["status", "champion", "completed_at", "round_started_at"]
        )
        return {"warnings": warnings, "completed": True}

    next_matches = _build_next_round(knockout, finalized)
    if not next_matches:
        knockout.status = StreakKnockout.Status.COMPLETE
        if winners:
            knockout.champion = winners[0]
        knockout.completed_at = now
        knockout.round_started_at = None
        knockout.save(
            update_fields=[
                "status",
                "champion",
                "completed_at",
                "round_started_at",
            ]
        )
        return {"warnings": warnings, "completed": True}

    knockout.current_round += 1
    next_round_start = round_start_at(challenge, knockout.current_round)
    knockout.round_started_at = next_round_start or now
    knockout.headstart_enabled = headstart_enabled
    knockout.save(
        update_fields=["current_round", "round_started_at", "headstart_enabled"]
    )
    return {"warnings": warnings, "completed": False}


def complete_knockout_on_competition_end(challenge: StreakChallenge) -> None:
    """Force-finish an in-progress knockout when the parent competition has ended."""
    if challenge.streak_competition.ended_at is None:
        return
    try:
        knockout = challenge.knockout
    except StreakKnockout.DoesNotExist:
        return
    if knockout.status == StreakKnockout.Status.COMPLETE:
        return

    participant_count = challenge.participants.count()
    total_rounds = knockout_total_rounds(participant_count)
    max_steps = max(total_rounds * 3, 8)

    for _ in range(max_steps):
        knockout.refresh_from_db()
        if knockout.status == StreakKnockout.Status.COMPLETE:
            return
        if knockout.status == StreakKnockout.Status.SETUP:
            headstart = headstart_for_round(challenge, 1)
        else:
            headstart = headstart_for_round(challenge, knockout.current_round + 1)
        try:
            advance_knockout_round(knockout, headstart_enabled=headstart)
        except ValueError:
            return


def complete_knockouts_for_competition(competition) -> None:
    """Complete knockouts for every challenge pool in an ended competition."""
    for challenge in StreakChallenge.objects.filter(streak_competition=competition):
        complete_knockout_on_competition_end(challenge)


def _round_window_end(
    challenge: StreakChallenge, round_index: int, now: datetime
) -> datetime:
    next_start = round_start_at(challenge, round_index + 1)
    if next_start is None:
        return now
    if timezone.is_naive(next_start):
        next_start = timezone.make_aware(next_start)
    if timezone.is_naive(now):
        now = timezone.make_aware(now)
    return min(now, next_start)


def _match_score_display_payload(
    knockout: StreakKnockout,
    match: StreakKnockoutMatch,
) -> dict[str, int | bool]:
    challenge = knockout.streak_challenge

    if match.finalized:
        bonus_enabled = headstart_for_round(challenge, match.round_index)
        score_a = match.score_a or 0
        score_b = match.score_b or 0
        score_a_correct, score_a_bonus = _score_breakdown_from_total(
            match.player_a,
            score_a,
            bonus_enabled=bonus_enabled,
        )
        score_b_correct, score_b_bonus = _score_breakdown_from_total(
            match.player_b,
            score_b,
            bonus_enabled=bonus_enabled,
        )
        return {
            "score_a": score_a,
            "score_b": score_b,
            "score_a_correct": score_a_correct,
            "score_b_correct": score_b_correct,
            "score_a_bonus": score_a_bonus,
            "score_b_bonus": score_b_bonus,
            "score_bonus_enabled": bonus_enabled,
        }

    now = timezone.now()

    if knockout.status == StreakKnockout.Status.SETUP:
        if match.round_index != 1:
            return {
                "score_a": 0,
                "score_b": 0,
                "score_a_correct": 0,
                "score_b_correct": 0,
                "score_a_bonus": 0,
                "score_b_bonus": 0,
                "score_bonus_enabled": False,
            }
        window_start = round_start_at(challenge, 1)
        if window_start is None:
            return {
                "score_a": 0,
                "score_b": 0,
                "score_a_correct": 0,
                "score_b_correct": 0,
                "score_a_bonus": 0,
                "score_b_bonus": 0,
                "score_bonus_enabled": False,
            }
        if timezone.is_naive(window_start):
            window_start = timezone.make_aware(window_start)
        if now < window_start:
            return {
                "score_a": 0,
                "score_b": 0,
                "score_a_correct": 0,
                "score_b_correct": 0,
                "score_a_bonus": 0,
                "score_b_bonus": 0,
                "score_bonus_enabled": False,
            }
        window_end = _round_window_end(challenge, 1, now)
        bonus_enabled = headstart_for_round(challenge, 1)
        score_a_correct = _correct_picks_in_window(
            knockout.streak_challenge_id,
            match.player_a.user_id,
            window_start,
            window_end,
        ) if match.player_a else 0
        score_b_correct = _correct_picks_in_window(
            knockout.streak_challenge_id,
            match.player_b.user_id,
            window_start,
            window_end,
        ) if match.player_b else 0
        score_a_bonus = (
            match.player_a.frozen_best_win_streak
            if match.player_a and bonus_enabled
            else 0
        )
        score_b_bonus = (
            match.player_b.frozen_best_win_streak
            if match.player_b and bonus_enabled
            else 0
        )
        return {
            "score_a": score_a_correct + score_a_bonus,
            "score_b": score_b_correct + score_b_bonus,
            "score_a_correct": score_a_correct,
            "score_b_correct": score_b_correct,
            "score_a_bonus": score_a_bonus,
            "score_b_bonus": score_b_bonus,
            "score_bonus_enabled": bonus_enabled,
        }

    if knockout.round_started_at is None:
        return {
            "score_a": 0,
            "score_b": 0,
            "score_a_correct": 0,
            "score_b_correct": 0,
            "score_a_bonus": 0,
            "score_b_bonus": 0,
            "score_bonus_enabled": False,
        }
    window_start = knockout.round_started_at
    if timezone.is_naive(window_start):
        window_start = timezone.make_aware(window_start)
    window_end = _round_window_end(challenge, knockout.current_round, now)
    score_a_correct = _correct_picks_in_window(
        knockout.streak_challenge_id,
        match.player_a.user_id,
        window_start,
        window_end,
    ) if match.player_a else 0
    score_b_correct = _correct_picks_in_window(
        knockout.streak_challenge_id,
        match.player_b.user_id,
        window_start,
        window_end,
    ) if match.player_b else 0
    score_a_bonus = (
        match.player_a.frozen_best_win_streak
        if match.player_a and knockout.headstart_enabled
        else 0
    )
    score_b_bonus = (
        match.player_b.frozen_best_win_streak
        if match.player_b and knockout.headstart_enabled
        else 0
    )
    return {
        "score_a": score_a_correct + score_a_bonus,
        "score_b": score_b_correct + score_b_bonus,
        "score_a_correct": score_a_correct,
        "score_b_correct": score_b_correct,
        "score_a_bonus": score_a_bonus,
        "score_b_bonus": score_b_bonus,
        "score_bonus_enabled": knockout.headstart_enabled,
    }


def _participant_slot(match: StreakKnockoutMatch, p: StreakParticipant) -> dict[str, Any]:
    return {
        "user_id": p.user_id,
        "display_name": streak_participant_label(p),
        "seed": p.knockout_seed,
    }


def _empty_match_payload(
    *,
    round_index: int,
    position: int,
    is_third_place: bool = False,
) -> dict[str, Any]:
    return {
        "id": -(round_index * 1000 + position),
        "round_index": round_index,
        "position": position,
        "is_third_place": is_third_place,
        "player_a": None,
        "player_b": None,
        "seed_a": 0,
        "seed_b": 0,
        "score_a": 0,
        "score_b": 0,
        "score_a_correct": 0,
        "score_b_correct": 0,
        "score_a_bonus": 0,
        "score_b_bonus": 0,
        "score_bonus_enabled": False,
        "winner_user_id": None,
        "finalized": False,
        "is_live": False,
    }


def _match_payload(knockout: StreakKnockout, match: StreakKnockoutMatch) -> dict[str, Any]:
    scores = _match_score_display_payload(knockout, match)
    challenge = knockout.streak_challenge
    now = timezone.now()
    round_one_start = round_start_at(challenge, 1)
    if round_one_start is not None and timezone.is_naive(round_one_start):
        round_one_start = timezone.make_aware(round_one_start)
    setup_live = (
        knockout.status == StreakKnockout.Status.SETUP
        and match.round_index == 1
        and not match.is_third_place
        and round_one_start is not None
        and now >= round_one_start
        and not match.finalized
    )
    participant_count = challenge.participants.count()
    total_rounds = knockout_total_rounds(participant_count)
    third_place_live = (
        match.is_third_place
        and not match.finalized
        and knockout.status == StreakKnockout.Status.IN_PROGRESS
        and knockout.current_round == total_rounds
    )
    is_live = third_place_live or setup_live or (
        not match.finalized
        and not match.is_third_place
        and knockout.status == StreakKnockout.Status.IN_PROGRESS
        and knockout.current_round == match.round_index
    )
    return {
        "id": match.id,
        "round_index": match.round_index,
        "position": match.position,
        "is_third_place": match.is_third_place,
        "player_a": _participant_slot(match, match.player_a)
        if match.player_a
        else None,
        "player_b": _participant_slot(match, match.player_b)
        if match.player_b
        else None,
        "seed_a": match.seed_a,
        "seed_b": match.seed_b,
        "score_a": scores["score_a"],
        "score_b": scores["score_b"],
        "score_a_correct": scores["score_a_correct"],
        "score_b_correct": scores["score_b_correct"],
        "score_a_bonus": scores["score_a_bonus"],
        "score_b_bonus": scores["score_b_bonus"],
        "score_bonus_enabled": scores["score_bonus_enabled"],
        "winner_user_id": match.winner.user_id if match.winner else None,
        "finalized": match.finalized,
        "is_live": is_live,
    }


def _season_ranks_by_user_id(
    participants: list[StreakParticipant],
) -> dict[int, int]:
    return {
        p.user_id: rank for p, rank in streak_ranked_participants(participants)
    }


def _consolation_row_sort_key(
    row: dict[str, Any],
    *,
    season_ranks: dict[int, int],
) -> tuple:
    return (
        -row["wins"],
        -row["win_pct"],
        season_ranks.get(row["user_id"], 999999),
        row["display_name"].casefold(),
    )


def _consolation_rows(
    challenge: StreakChallenge, knockout: StreakKnockout
) -> list[dict[str, Any]]:
    participants = list(
        StreakParticipant.objects.filter(streak_challenge=challenge).select_related(
            "user"
        )
    )
    season_ranks = _season_ranks_by_user_id(participants)
    rows: list[dict[str, Any]] = []
    for p in StreakParticipant.objects.filter(
        streak_challenge=challenge,
        consolation_eligible_from__isnull=False,
    ).select_related("user"):
        if knockout.champion_id == p.id:
            continue
        answered = p.consolation_wins + p.consolation_losses
        rate = p.consolation_wins / answered if answered else 0.0
        rows.append(
            {
                "user_id": p.user_id,
                "display_name": streak_participant_label(p),
                "wins": p.consolation_wins,
                "losses": p.consolation_losses,
                "record": f"{p.consolation_wins}-{p.consolation_losses}",
                "win_pct": round(rate * 100),
            }
        )
    rows.sort(key=lambda r: _consolation_row_sort_key(r, season_ranks=season_ranks))
    return rows


def _projected_consolation_rows(
    participants: list[StreakParticipant], qualifier_ids: set[int]
) -> list[dict[str, Any]]:
    season_ranks = _season_ranks_by_user_id(participants)
    rows: list[dict[str, Any]] = []
    for p in participants:
        if p.id in qualifier_ids:
            continue
        rows.append(
            {
                "user_id": p.user_id,
                "display_name": streak_participant_label(p),
                "wins": 0,
                "losses": 0,
                "record": "0-0",
                "win_pct": 0,
            }
        )
    rows.sort(key=lambda r: _consolation_row_sort_key(r, season_ranks=season_ranks))
    return rows


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def knockout_header_summary(
    challenge: StreakChallenge, participant: StreakParticipant | None
) -> dict[str, str] | None:
    if participant is None or not challenge.is_knockout:
        return None
    try:
        knockout = challenge.knockout
    except StreakKnockout.DoesNotExist:
        return None

    third_place_match = knockout.matches.filter(is_third_place=True).first()
    if third_place_match is not None and (
        third_place_match.player_a_id == participant.id
        or third_place_match.player_b_id == participant.id
    ):
        scores = _match_score_display_payload(knockout, third_place_match)
        name_a = (
            streak_participant_label(third_place_match.player_a)
            if third_place_match.player_a
            else "TBD"
        )
        name_b = (
            streak_participant_label(third_place_match.player_b)
            if third_place_match.player_b
            else "TBD"
        )
        return {
            "kind": "matchup",
            "label": "3rd Place",
            "value": f"{name_a} {scores['score_a']}-{scores['score_b']} {name_b}",
        }

    if not participant.in_knockout_bracket and knockout.champion_id != participant.id:
        rows = _consolation_rows(challenge, knockout)
        rank = next(
            (idx + 1 for idx, row in enumerate(rows) if row["user_id"] == participant.user_id),
            None,
        )
        label = "CONSOLATION"
        if rank is not None:
            label = f"{label} {_ordinal(rank)}"
        return {
            "kind": "consolation",
            "label": label,
            "value": f"{participant.consolation_wins}-{participant.consolation_losses}",
        }

    participant_matches = list(
        knockout.matches.filter(player_a=participant, is_third_place=False).select_related(
            "player_a__user", "player_b__user", "winner__user"
        )
    ) + list(
        knockout.matches.filter(player_b=participant, is_third_place=False).select_related(
            "player_a__user", "player_b__user", "winner__user"
        )
    )
    if not participant_matches:
        return None

    participant_matches.sort(
        key=lambda m: (
            0 if not m.finalized else 1,
            -m.round_index,
            m.position,
        )
    )
    match = participant_matches[0]
    scores = _match_score_display_payload(knockout, match)
    total_rounds = knockout_total_rounds(challenge.participants.count())
    name_a = streak_participant_label(match.player_a) if match.player_a else "TBD"
    name_b = streak_participant_label(match.player_b) if match.player_b else "TBD"
    return {
        "kind": "matchup",
        "label": knockout_round_label(match.round_index, total_rounds),
        "value": f"{name_a} {scores['score_a']}-{scores['score_b']} {name_b}",
    }


def projected_knockout_payload(challenge: StreakChallenge) -> dict[str, Any] | None:
    participants = list(
        StreakParticipant.objects.filter(streak_challenge=challenge).select_related("user")
    )
    if len(participants) < 2:
        return None

    seeded = _seed_participants(participants)
    bracket_size = bracket_qualifier_count(len(seeded))
    if bracket_size < 2:
        return None

    qualifiers = seeded[:bracket_size]
    qualifier_ids = {p.id for p, _seed in qualifiers}
    by_seed = _participant_by_seed(qualifiers)
    total_rounds = knockout_total_rounds(len(participants))
    round_one_bonus_enabled = headstart_for_round(challenge, 1)
    rounds: list[dict[str, Any]] = []

    first_round_matches: list[dict[str, Any]] = []
    for position, (seed_a, seed_b) in enumerate(
        first_round_seed_pairs(bracket_size), start=1
    ):
        player_a = by_seed.get(seed_a)
        player_b = by_seed.get(seed_b)
        score_a_bonus = player_a.best_win_streak if player_a and round_one_bonus_enabled else 0
        score_b_bonus = player_b.best_win_streak if player_b and round_one_bonus_enabled else 0
        first_round_matches.append(
            {
                "id": -(1000 + position),
                "round_index": 1,
                "position": position,
                "player_a": {
                    "user_id": player_a.user_id,
                    "display_name": streak_participant_label(player_a),
                    "seed": seed_a,
                }
                if player_a
                else None,
                "player_b": {
                    "user_id": player_b.user_id,
                    "display_name": streak_participant_label(player_b),
                    "seed": seed_b,
                }
                if player_b
                else None,
                "seed_a": seed_a,
                "seed_b": seed_b,
                "score_a": score_a_bonus,
                "score_b": score_b_bonus,
                "score_a_correct": 0,
                "score_b_correct": 0,
                "score_a_bonus": score_a_bonus,
                "score_b_bonus": score_b_bonus,
                "score_bonus_enabled": round_one_bonus_enabled,
                "winner_user_id": None,
                "finalized": False,
                "is_live": False,
            }
        )
    rounds.append({"round_index": 1, "matches": first_round_matches})

    for round_index in range(2, total_rounds + 1):
        matches = [
            _empty_match_payload(round_index=round_index, position=position)
            for position in range(1, _matches_in_round(bracket_size, round_index) + 1)
        ]
        rounds.append({"round_index": round_index, "matches": matches})

    third_place_payload = None
    if third_place_match_enabled(challenge, len(participants)):
        third_place_payload = _empty_match_payload(
            round_index=total_rounds,
            position=2,
            is_third_place=True,
        )

    return {
        "status": "SETUP",
        "current_round": 0,
        "headstart_enabled": False,
        "champion_user_id": None,
        "third_place_winner_user_id": None,
        "third_place_match": third_place_payload,
        "third_place_match_enabled": third_place_match_enabled(
            challenge, len(participants)
        ),
        "total_rounds": total_rounds,
        "rounds": rounds,
        "consolation": _projected_consolation_rows(participants, qualifier_ids),
        "can_manage": False,
        "projected": True,
    }


def knockout_payload(challenge: StreakChallenge) -> dict[str, Any] | None:
    knockout = getattr(challenge, "knockout", None)
    if knockout is None:
        try:
            knockout = challenge.knockout
        except StreakKnockout.DoesNotExist:
            return None

    participant_count = challenge.participants.count()
    total_rounds = knockout_total_rounds(participant_count)
    bracket_size = bracket_qualifier_count(max(participant_count, 2))
    matches = list(
        knockout.matches.select_related(
            "player_a__user",
            "player_b__user",
            "winner__user",
        )
        .filter(is_third_place=False)
        .order_by("round_index", "position")
    )
    third_place_match = (
        knockout.matches.filter(is_third_place=True)
        .select_related("player_a__user", "player_b__user", "winner__user")
        .first()
    )
    rounds: dict[int, list[dict[str, Any]]] = {}
    for match in matches:
        rounds.setdefault(match.round_index, []).append(_match_payload(knockout, match))

    round_rows: list[dict[str, Any]] = []
    for idx in range(1, total_rounds + 1):
        existing = {m["position"]: m for m in rounds.get(idx, [])}
        match_count = _matches_in_round(bracket_size, idx)
        match_rows = [
            existing.get(position)
            or _empty_match_payload(round_index=idx, position=position)
            for position in range(1, match_count + 1)
        ]
        round_rows.append({"round_index": idx, "matches": match_rows})

    consolation_rows = _consolation_rows(challenge, knockout)
    third_place_on = third_place_match_enabled(challenge, participant_count)
    if third_place_match is not None:
        third_place_payload = _match_payload(knockout, third_place_match)
    elif third_place_on:
        third_place_payload = _empty_match_payload(
            round_index=total_rounds,
            position=2,
            is_third_place=True,
        )
    else:
        third_place_payload = None

    return {
        "status": knockout.status,
        "current_round": knockout.current_round,
        "headstart_enabled": knockout.headstart_enabled,
        "champion_user_id": knockout.champion.user_id if knockout.champion else None,
        "third_place_winner_user_id": (
            third_place_match.winner.user_id
            if third_place_match and third_place_match.winner
            else None
        ),
        "third_place_match": third_place_payload,
        "third_place_match_enabled": third_place_on,
        "total_rounds": total_rounds,
        "rounds": round_rows,
        "consolation": consolation_rows,
        "can_manage": False,
        "projected": False,
    }


def _participant_counts_for_consolation(
    participant: StreakParticipant,
    closes_at: datetime,
) -> bool:
    if participant.consolation_eligible_from is None:
        return False
    eligible_from = participant.consolation_eligible_from
    if timezone.is_naive(closes_at):
        closes_at = timezone.make_aware(closes_at)
    if timezone.is_naive(eligible_from):
        eligible_from = timezone.make_aware(eligible_from)
    if closes_at < eligible_from:
        return False
    if participant.in_knockout_bracket and participant.bracket_eliminated_at is None:
        return False
    return True


def recalculate_consolation_for_challenge(challenge: StreakChallenge) -> None:
    """Rebuild consolation W-L from resolved picks (every question counts)."""
    if not challenge.is_knockout:
        return

    questions = list(
        StreakQuestion.objects.filter(
            streak_competition_id=challenge.streak_competition_id,
            resolved_at__isnull=False,
            correct_choice_id__isnull=False,
        ).order_by("closes_at", "order", "id")
    )
    question_ids = [q.id for q in questions]
    participants = list(
        StreakParticipant.objects.filter(streak_challenge=challenge).select_related(
            "user"
        )
    )

    for participant in participants:
        picks_by_q = {
            p.question_id: p
            for p in StreakPick.objects.filter(
                streak_challenge_id=challenge.id,
                user_id=participant.user_id,
                question_id__in=question_ids,
            )
        }

        wins = 0
        losses = 0
        for q in questions:
            pick = picks_by_q.get(q.id)
            if pick is None:
                continue
            if not _participant_counts_for_consolation(participant, q.closes_at):
                continue
            if _is_correct(pick, q):
                wins += 1
            else:
                losses += 1

        if (
            participant.consolation_wins != wins
            or participant.consolation_losses != losses
        ):
            participant.consolation_wins = wins
            participant.consolation_losses = losses
            participant.save(update_fields=["consolation_wins", "consolation_losses"])


def update_consolation_for_question(
    challenge: StreakChallenge, question: StreakQuestion
) -> None:
    if not challenge.is_knockout:
        return
    if question.resolved_at is None or question.correct_choice_id is None:
        return
    recalculate_consolation_for_challenge(challenge)
