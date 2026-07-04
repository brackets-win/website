"""Directional streak stats for streak challenges."""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from brackets.models import StreakParticipant, StreakPick, StreakQuestion, StreakQuestionChoice
from brackets.utils.streak_deadlines import closes_at_key
from brackets.utils.streak_knockout_rules import streak_season_cutoff_at


def _is_correct(pick: StreakPick, question: StreakQuestion) -> bool:
    return (
        question.correct_choice_id is not None
        and pick.choice_id == question.correct_choice_id
    )


def _apply_batch(streak_signed: int, wins: int, losses: int) -> int:
    """
    Update signed streak after resolving a batch of picks at the same close time.

    Mixed results reset to a win streak equal to the number of correct picks in
    the batch; all wins extend W; all losses extend L.
    """
    if wins == 0 and losses == 0:
        return streak_signed
    if losses == 0:
        if streak_signed >= 0:
            return streak_signed + wins
        return wins
    if wins == 0:
        if streak_signed <= 0:
            return streak_signed - losses
        return -losses
    return wins


def _one_pick_per_deadline(
    questions: list[StreakQuestion],
    picks_by_q: dict[int, StreakPick],
) -> list[tuple[StreakQuestion, StreakPick]]:
    """Streak season: at most one scored pick per deadline."""
    deadline_pick: dict[datetime, tuple[StreakQuestion, StreakPick]] = {}
    for q in questions:
        pick = picks_by_q.get(q.id)
        if pick is None:
            continue
        key = closes_at_key(q.closes_at)
        prev = deadline_pick.get(key)
        if prev is None or (q.order, q.id) < (prev[0].order, prev[0].id):
            deadline_pick[key] = (q, pick)
    return [deadline_pick[k] for k in sorted(deadline_pick.keys())]


def recalculate_participant_stats(participant: StreakParticipant) -> None:
    challenge = participant.streak_challenge
    competition_id = challenge.streak_competition_id
    questions = list(
        StreakQuestion.objects.filter(
            streak_competition_id=competition_id,
            resolved_at__isnull=False,
            correct_choice_id__isnull=False,
        ).order_by("closes_at", "order", "id")
    )
    picks_by_q = {
        p.question_id: p
        for p in StreakPick.objects.filter(
            streak_challenge_id=participant.streak_challenge_id,
            user_id=participant.user_id,
            question_id__in=[q.id for q in questions],
        ).select_related("choice")
    }

    cutoff = streak_season_cutoff_at(challenge) if challenge.is_knockout else None
    if cutoff is not None:
        season_questions = [q for q in questions if q.closes_at < cutoff]
        post_cutoff_questions = [q for q in questions if q.closes_at >= cutoff]
    else:
        season_questions = questions
        post_cutoff_questions = []

    season_scored = _one_pick_per_deadline(season_questions, picks_by_q)

    wins = 0
    losses = 0
    streak_signed = 0
    best_win_streak = 0
    best_loss_streak = 0

    for q, pick in season_scored:
        if _is_correct(pick, q):
            wins += 1
            batch_wins = 1
            batch_losses = 0
        else:
            losses += 1
            batch_wins = 0
            batch_losses = 1
        streak_signed = _apply_batch(streak_signed, batch_wins, batch_losses)
        if streak_signed > 0:
            best_win_streak = max(best_win_streak, streak_signed)
        elif streak_signed < 0:
            best_loss_streak = max(best_loss_streak, -streak_signed)

    # Knockout/consolation: every resolved question counts toward total record.
    for q in post_cutoff_questions:
        pick = picks_by_q.get(q.id)
        if pick is None:
            continue
        if _is_correct(pick, q):
            wins += 1
        else:
            losses += 1

    participant.wins = wins
    participant.losses = losses
    participant.streak_signed = streak_signed
    participant.best_win_streak = best_win_streak
    participant.best_loss_streak = best_loss_streak
    participant.save(
        update_fields=[
            "wins",
            "losses",
            "streak_signed",
            "best_win_streak",
            "best_loss_streak",
        ]
    )


def season_streak_signed(participant: StreakParticipant) -> int:
    if participant.streak_challenge.is_knockout:
        return participant.frozen_streak_signed
    return participant.streak_signed


def season_best_win_streak(participant: StreakParticipant) -> int:
    if participant.streak_challenge.is_knockout:
        return participant.frozen_best_win_streak
    return participant.best_win_streak


def season_best_loss_streak(participant: StreakParticipant) -> int:
    if participant.streak_challenge.is_knockout:
        return participant.frozen_best_loss_streak
    return participant.best_loss_streak


def current_broken_win_streak(participant: StreakParticipant) -> int:
    """
    Length of the win streak that was just broken, when the current streak is 1L.

    Returns 0 for every other state.
    """
    if participant.streak_challenge.is_knockout:
        return season_broken_win_streak(participant)
    return _broken_win_streak_from_picks(participant, participant.streak_signed)


def season_broken_win_streak(participant: StreakParticipant) -> int:
    streak_signed = season_streak_signed(participant)
    if streak_signed != -1:
        return 0
    return _broken_win_streak_from_picks(participant, streak_signed)


def _broken_win_streak_from_picks(
    participant: StreakParticipant,
    streak_signed: int,
) -> int:
    if streak_signed != -1:
        return 0

    competition_id = participant.streak_challenge.streak_competition_id
    questions_qs = StreakQuestion.objects.filter(
        streak_competition_id=competition_id,
        resolved_at__isnull=False,
        correct_choice_id__isnull=False,
    )
    if participant.streak_challenge.is_knockout:
        cutoff = streak_season_cutoff_at(participant.streak_challenge)
        if cutoff is not None:
            questions_qs = questions_qs.filter(closes_at__lt=cutoff)
    questions = list(questions_qs.order_by("closes_at", "order", "id"))
    picks_by_q = {
        p.question_id: p
        for p in StreakPick.objects.filter(
            streak_challenge_id=participant.streak_challenge_id,
            user_id=participant.user_id,
            question_id__in=[q.id for q in questions],
        ).select_related("choice")
    }

    season_scored = _one_pick_per_deadline(questions, picks_by_q)

    streak_signed = 0
    broken_streak = 0
    for q, pick in season_scored:
        previous_streak = streak_signed
        if _is_correct(pick, q):
            streak_signed = _apply_batch(streak_signed, 1, 0)
        else:
            streak_signed = _apply_batch(streak_signed, 0, 1)
            broken_streak = previous_streak if previous_streak >= 3 else 0

    return broken_streak if streak_signed == -1 else 0


def recalculate_streak_challenge(streak_challenge_id: int) -> None:
    with transaction.atomic():
        for participant in StreakParticipant.objects.filter(
            streak_challenge_id=streak_challenge_id
        ).select_related("streak_challenge"):
            recalculate_participant_stats(participant)


def recalculate_streak_competition(streak_competition_id: int) -> None:
    from brackets.models import StreakChallenge

    challenge_ids = StreakChallenge.objects.filter(
        streak_competition_id=streak_competition_id
    ).values_list("id", flat=True)
    for challenge_id in challenge_ids:
        recalculate_streak_challenge(challenge_id)


def update_knockout_consolation_for_question(question: StreakQuestion) -> None:
    from brackets.models import StreakChallenge
    from brackets.utils.streak_knockout import update_consolation_for_question

    if question.resolved_at is None or question.correct_choice_id is None:
        return
    for challenge in StreakChallenge.objects.filter(
        streak_competition_id=question.streak_competition_id,
        mode=StreakChallenge.Mode.KNOCKOUT,
    ):
        update_consolation_for_question(challenge, question)


def clear_question_resolution(question: StreakQuestion) -> None:
    """Remove the correct answer and reopen the question (e.g. accidental admin pick)."""
    from brackets.utils.streak_challenge_stats import bump_streak_stats_for_competition

    question.correct_choice = None
    question.resolved_at = None
    question.save(update_fields=["correct_choice", "resolved_at"])
    recalculate_streak_competition(question.streak_competition_id)
    update_knockout_consolation_for_question(question)
    bump_streak_stats_for_competition(question.streak_competition_id)


def resolve_question(question: StreakQuestion, correct_choice_id: int) -> None:
    from brackets.utils.streak_challenge_stats import bump_streak_stats_for_competition

    choice = StreakQuestionChoice.objects.filter(
        pk=correct_choice_id, question_id=question.id
    ).first()
    if choice is None:
        raise ValueError("correct_choice_id is invalid for this question")
    question.correct_choice = choice
    update_fields = ["correct_choice"]
    if question.resolved_at is None:
        question.resolved_at = timezone.now()
        update_fields.append("resolved_at")
    question.save(update_fields=update_fields)
    recalculate_streak_competition(question.streak_competition_id)
    update_knockout_consolation_for_question(question)
    bump_streak_stats_for_competition(question.streak_competition_id)
