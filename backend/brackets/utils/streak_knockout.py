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
    round_start_at,
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


def _seed_participants(
    participants: list[StreakParticipant],
) -> list[tuple[StreakParticipant, int]]:
    answered = [p for p in participants if p.wins + p.losses > 0]
    if answered:
        ranked = streak_ranked_participants(participants)
        return [(p, rank) for p, rank in ranked]

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
    challenge.mode = StreakChallenge.Mode.KNOCKOUT
    challenge.save(update_fields=["mode"])

    seeded = _seed_participants(participants)
    bracket_size = bracket_qualifier_count(len(seeded))
    qualifiers = seeded[:bracket_size]
    by_seed = _participant_by_seed(qualifiers)

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


def _finalize_round(
    knockout: StreakKnockout,
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[StreakKnockoutMatch]:
    matches = list(
        knockout.matches.filter(
            round_index=knockout.current_round,
            finalized=False,
        ).select_related("player_a", "player_b")
    )
    now = window_end
    for match in matches:
        score_a = _match_score(
            match.player_a,
            challenge_id=knockout.streak_challenge_id,
            window_start=window_start,
            window_end=window_end,
            headstart_enabled=knockout.headstart_enabled,
        )
        score_b = _match_score(
            match.player_b,
            challenge_id=knockout.streak_challenge_id,
            window_start=window_start,
            window_end=window_end,
            headstart_enabled=knockout.headstart_enabled,
        )
        winner = _pick_winner(match, score_a, score_b)
        match.score_a = score_a
        match.score_b = score_b
        match.winner = winner
        match.finalized = True
        match.save(
            update_fields=["score_a", "score_b", "winner", "finalized"]
        )

        for player in (match.player_a, match.player_b):
            if player is None or winner is None:
                continue
            if player.id != winner.id:
                player.bracket_eliminated_at = now
                player.consolation_eligible_from = now
                player.in_knockout_bracket = False
                player.save(
                    update_fields=[
                        "bracket_eliminated_at",
                        "consolation_eligible_from",
                        "in_knockout_bracket",
                    ]
                )

    return matches


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


def _live_match_scores(
    knockout: StreakKnockout,
    match: StreakKnockoutMatch,
) -> tuple[int, int]:
    if match.finalized:
        return match.score_a or 0, match.score_b or 0

    challenge = knockout.streak_challenge
    now = timezone.now()

    if knockout.status == StreakKnockout.Status.SETUP:
        if match.round_index != 1:
            return 0, 0
        window_start = round_start_at(challenge, 1)
        if window_start is None:
            return 0, 0
        if timezone.is_naive(window_start):
            window_start = timezone.make_aware(window_start)
        if now < window_start:
            return 0, 0
        window_end = _round_window_end(challenge, 1, now)
        headstart = headstart_for_round(challenge, 1)
        score_a = _match_score(
            match.player_a,
            challenge_id=knockout.streak_challenge_id,
            window_start=window_start,
            window_end=window_end,
            headstart_enabled=headstart,
        )
        score_b = _match_score(
            match.player_b,
            challenge_id=knockout.streak_challenge_id,
            window_start=window_start,
            window_end=window_end,
            headstart_enabled=headstart,
        )
        return score_a, score_b

    if knockout.round_started_at is None:
        return 0, 0
    window_start = knockout.round_started_at
    if timezone.is_naive(window_start):
        window_start = timezone.make_aware(window_start)
    window_end = _round_window_end(challenge, knockout.current_round, now)
    score_a = _match_score(
        match.player_a,
        challenge_id=knockout.streak_challenge_id,
        window_start=window_start,
        window_end=window_end,
        headstart_enabled=knockout.headstart_enabled,
    )
    score_b = _match_score(
        match.player_b,
        challenge_id=knockout.streak_challenge_id,
        window_start=window_start,
        window_end=window_end,
        headstart_enabled=knockout.headstart_enabled,
    )
    return score_a, score_b


def _participant_slot(match: StreakKnockoutMatch, p: StreakParticipant) -> dict[str, Any]:
    return {
        "user_id": p.user_id,
        "display_name": streak_participant_label(p),
        "seed": p.knockout_seed,
    }


def _match_payload(knockout: StreakKnockout, match: StreakKnockoutMatch) -> dict[str, Any]:
    score_a, score_b = _live_match_scores(knockout, match)
    challenge = knockout.streak_challenge
    now = timezone.now()
    round_one_start = round_start_at(challenge, 1)
    if round_one_start is not None and timezone.is_naive(round_one_start):
        round_one_start = timezone.make_aware(round_one_start)
    setup_live = (
        knockout.status == StreakKnockout.Status.SETUP
        and match.round_index == 1
        and round_one_start is not None
        and now >= round_one_start
        and not match.finalized
    )
    is_live = setup_live or (
        not match.finalized
        and knockout.status == StreakKnockout.Status.IN_PROGRESS
        and knockout.current_round == match.round_index
    )
    return {
        "id": match.id,
        "round_index": match.round_index,
        "position": match.position,
        "player_a": _participant_slot(match, match.player_a)
        if match.player_a
        else None,
        "player_b": _participant_slot(match, match.player_b)
        if match.player_b
        else None,
        "seed_a": match.seed_a,
        "seed_b": match.seed_b,
        "score_a": score_a,
        "score_b": score_b,
        "winner_user_id": match.winner.user_id if match.winner else None,
        "finalized": match.finalized,
        "is_live": is_live,
    }


def knockout_payload(challenge: StreakChallenge) -> dict[str, Any] | None:
    knockout = getattr(challenge, "knockout", None)
    if knockout is None:
        try:
            knockout = challenge.knockout
        except StreakKnockout.DoesNotExist:
            return None

    matches = list(
        knockout.matches.select_related(
            "player_a__user",
            "player_b__user",
            "winner__user",
        ).order_by("round_index", "position")
    )
    rounds: dict[int, list[dict[str, Any]]] = {}
    for match in matches:
        rounds.setdefault(match.round_index, []).append(_match_payload(knockout, match))

    consolation_rows: list[dict[str, Any]] = []
    for p in StreakParticipant.objects.filter(
        streak_challenge=challenge,
        consolation_eligible_from__isnull=False,
    ).select_related("user"):
        if knockout.champion_id == p.id:
            continue
        answered = p.consolation_wins + p.consolation_losses
        rate = p.consolation_wins / answered if answered else 0.0
        consolation_rows.append(
            {
                "user_id": p.user_id,
                "display_name": streak_participant_label(p),
                "wins": p.consolation_wins,
                "losses": p.consolation_losses,
                "record": f"{p.consolation_wins}-{p.consolation_losses}",
                "win_pct": round(rate * 100),
            }
        )
    consolation_rows.sort(
        key=lambda r: (-r["wins"], -r["win_pct"], r["display_name"].casefold())
    )

    return {
        "status": knockout.status,
        "current_round": knockout.current_round,
        "headstart_enabled": knockout.headstart_enabled,
        "champion_user_id": knockout.champion.user_id if knockout.champion else None,
        "rounds": [
            {"round_index": idx, "matches": rounds[idx]}
            for idx in sorted(rounds.keys())
        ],
        "consolation": consolation_rows,
        "can_manage": False,
    }


def update_consolation_for_question(
    challenge: StreakChallenge, question: StreakQuestion
) -> None:
    if not challenge.is_knockout:
        return
    if question.resolved_at is None or question.correct_choice_id is None:
        return

    closes_at = question.closes_at
    participants = StreakParticipant.objects.filter(
        streak_challenge=challenge,
        consolation_eligible_from__isnull=False,
        consolation_eligible_from__lte=closes_at,
    )
    picks_by_user = {
        p.user_id: p
        for p in StreakPick.objects.filter(
            streak_challenge=challenge,
            question=question,
        )
    }
    for participant in participants:
        if participant.bracket_eliminated_at is None and participant.in_knockout_bracket:
            continue
        pick = picks_by_user.get(participant.user_id)
        if pick is None:
            continue
        if _is_correct(pick, question):
            participant.consolation_wins += 1
            participant.save(update_fields=["consolation_wins"])
        else:
            participant.consolation_losses += 1
            participant.save(update_fields=["consolation_losses"])
