"""Streak competition and challenge API."""

from __future__ import annotations

import json
from typing import Any

from django.db import DatabaseError, IntegrityError, transaction
from collections import defaultdict

from django.db.models import Count
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from brackets.api import serializers
from brackets.api.views import (
    _generate_join_code,
    _is_multipart,
    _json_error,
    _multipart_post_files,
    _normalize_display_name,
    _normalize_join_code,
    _parse_json,
    _require_user,
)
from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakKnockout,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
    StreakQuestionChoice,
)
from brackets.utils.leaderboard_preview import (
    streak_challenge_leaderboard_preview,
    streak_participant_label,
    streak_ranked_participants,
)
from brackets.utils.streak_awards import compute_streak_awards
from brackets.utils.streak_deadlines import (
    closes_at_key,
    open_deadline_pick_map,
    other_open_pick_at_same_deadline,
)
from brackets.utils.streak_knockout_rules import (
    is_knockout_pick,
    knockout_phase_for_closes_at,
    knockout_phases_payload,
    knockout_third_place_supported,
    knockout_third_place_setting_editable,
    knockout_total_rounds,
    participant_in_knockout_bracket_at,
    question_visible_in_challenge,
    round_start_at,
    streak_season_cutoff_at,
    validate_knockout_schedule,
)
from brackets.utils.streak_knockout_schedule import process_scheduled_knockout
from brackets.utils.streak_scoring import (
    clear_question_resolution,
    recalculate_streak_challenge,
    recalculate_streak_competition,
    resolve_question,
    season_best_loss_streak,
    season_best_win_streak,
    season_broken_win_streak,
    season_streak_signed,
)
from brackets.utils.streak_knockout import (
    knockout_header_summary,
    projected_knockout_payload,
    recalculate_consolation_for_challenge,
)


def _streak_participant_or_none(challenge: StreakChallenge, user):
    return StreakParticipant.objects.filter(
        streak_challenge=challenge, user=user
    ).first()


def _assert_streak_member(challenge: StreakChallenge, user) -> StreakParticipant:
    p = _streak_participant_or_none(challenge, user)
    if p is None:
        raise PermissionError("Not a participant")
    return p


def _competition_public(
    c: StreakCompetition, *, challenge_count: int | None = None
) -> dict[str, Any]:
    if challenge_count is None:
        if hasattr(c, "challenge_count"):
            challenge_count = c.challenge_count
        else:
            challenge_count = c.challenges.count()
    return {
        "id": c.id,
        "name": c.name,
        "image_url": serializers.streak_competition_image_url(c),
        "question_count": c.questions.count(),
        "challenge_count": challenge_count,
        "ended_at": c.ended_at.isoformat() if c.ended_at else None,
        "is_over": c.ended_at is not None,
    }


def _streak_summary(
    c: StreakChallenge, user, *, participant: StreakParticipant | None = None
) -> dict[str, Any]:
    if participant is None:
        participant = _streak_participant_or_none(c, user)
    creator = ""
    if c.created_by_id and getattr(c, "created_by", None) is not None:
        creator = (c.created_by.username or "").strip()
    competition = (
        c.streak_competition
        if c.streak_competition_id and getattr(c, "streak_competition", None) is not None
        else None
    )
    competition_name = competition.name if competition is not None else ""
    return {
        "id": c.id,
        "name": c.name,
        "streak_competition_id": c.streak_competition_id,
        "streak_competition_name": competition_name,
        "image_url": serializers.streak_competition_image_url(competition)
        if competition is not None
        else None,
        "created_by_username": creator,
        "leaderboard_preview": streak_challenge_leaderboard_preview(c, user),
        "is_public": c.is_public,
        "is_private": not c.is_public,
        "join_code": c.join_code if not c.is_public else None,
        "is_participant": participant is not None,
        "wins": participant.wins if participant else 0,
        "losses": participant.losses if participant else 0,
        "streak_signed": season_streak_signed(participant) if participant else 0,
        "best_win_streak": season_best_win_streak(participant) if participant else 0,
        "broken_win_streak": (
            season_broken_win_streak(participant) if participant else 0
        ),
        "streak_display": serializers.streak_display(
            season_streak_signed(participant) if participant else 0
        ),
        "current_display": serializers.streak_display(
            season_streak_signed(participant) if participant else 0
        ),
        "long_win_display": _long_streak_display(
            season_best_win_streak(participant) if participant else 0, kind="win"
        ),
        "is_creator": c.created_by_id == user.id,
        "competition_is_over": competition.is_over if competition is not None else False,
        "competition_ended_at": competition.ended_at.isoformat()
        if competition is not None and competition.ended_at
        else None,
        "mode": c.mode,
        "is_knockout": c.is_knockout,
        "knockout_transition_at": c.knockout_transition_at.isoformat()
        if c.knockout_transition_at
        else None,
        "knockout_round_starts": c.knockout_round_starts or {},
        "knockout_round_headstart": c.knockout_round_headstart or {},
        "knockout_third_place_match": c.knockout_third_place_match,
        "knockout_third_place_editable": knockout_third_place_setting_editable(c),
        "knockout_total_rounds": knockout_total_rounds(
            StreakParticipant.objects.filter(streak_challenge=c).count()
        ),
        "knockout_header": knockout_header_summary(c, participant),
    }


def _pick_stats_by_question(
    streak_challenge_id: int, question_ids: list[int]
) -> dict[int, dict[int, dict[str, int]]]:
    """question_id -> choice_id -> {count, pick_pct} for this challenge."""
    if not question_ids:
        return {}
    rows = (
        StreakPick.objects.filter(
            streak_challenge_id=streak_challenge_id,
            question_id__in=question_ids,
        )
        .values("question_id", "choice_id")
        .annotate(count=Count("id"))
    )
    counts: dict[int, dict[int, int]] = defaultdict(dict)
    for row in rows:
        counts[row["question_id"]][row["choice_id"]] = row["count"]
    result: dict[int, dict[int, dict[str, int]]] = {}
    for question_id, choice_counts in counts.items():
        total = sum(choice_counts.values())
        if total == 0:
            result[question_id] = {}
            continue
        result[question_id] = {
            choice_id: {
                "count": count,
                "pick_pct": round(count * 100 / total),
            }
            for choice_id, count in choice_counts.items()
        }
    return result


def _choices_payload(
    question: StreakQuestion,
    pick_stats: dict[int, dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for choice in question.choices.all():
        item: dict[str, Any] = {"id": choice.id, "label": choice.label}
        if pick_stats is not None:
            stats = pick_stats.get(choice.id, {})
            item["pick_count"] = stats.get("count", 0)
            item["pick_pct"] = stats.get("pick_pct", 0)
        rows.append(item)
    return rows


def _question_public(
    q: StreakQuestion,
    user,
    streak_challenge_id: int,
    *,
    challenge: StreakChallenge,
    deadline_picks: dict | None = None,
    pick_stats: dict[int, dict[str, int]] | None = None,
    participant_count: int = 0,
) -> dict[str, Any]:
    pick = (
        StreakPick.objects.filter(
            question=q, user=user, streak_challenge_id=streak_challenge_id
        )
        .select_related("choice")
        .first()
    )
    correct_label = q.correct_choice.label if q.correct_choice_id else None
    now = timezone.now()
    is_open = q.resolved_at is None and q.closes_at > now
    knockout_pick = is_knockout_pick(challenge, q)
    locked_by_question_id = None
    deadline_locked = False
    if is_open and deadline_picks is not None and not knockout_pick:
        locked_by_question_id = deadline_picks.get(closes_at_key(q.closes_at))
        deadline_locked = (
            locked_by_question_id is not None
            and locked_by_question_id != q.id
            and pick is None
        )
    phase = knockout_phase_for_closes_at(challenge, q.closes_at, participant_count)
    return {
        "id": q.id,
        "text": q.text,
        "closes_at": q.closes_at.isoformat(),
        "resolved_at": q.resolved_at.isoformat() if q.resolved_at else None,
        "choices": _choices_payload(
            q, pick_stats if q.resolved_at is not None else None
        ),
        "correct_choice_id": q.correct_choice_id,
        "correct_answer": correct_label,
        "user_choice_id": pick.choice_id if pick else None,
        "user_answer": pick.choice.label if pick else None,
        "is_open": is_open,
        "deadline_locked": deadline_locked,
        "locked_by_question_id": locked_by_question_id,
        "can_clear_pick": is_open and pick is not None,
        "knockout_only": q.knockout_only,
        "is_knockout_pick": knockout_pick,
        "knockout_phase_label": phase["label"] if phase else None,
        "knockout_phase_starts_at": phase["starts_at"].isoformat() if phase else None,
    }


def _long_streak_display(value: int, *, kind: str) -> str:
    if value <= 0:
        return "—"
    if kind == "win":
        return serializers.streak_display(value)
    return f"{value}L"


def _participant_in_third_place_match(
    challenge: StreakChallenge, participant: StreakParticipant
) -> bool:
    try:
        knockout = challenge.knockout
    except StreakKnockout.DoesNotExist:
        return False
    match = knockout.matches.filter(is_third_place=True).first()
    if match is None:
        return False
    return participant.id in (match.player_a_id, match.player_b_id)


def _participant_pick_section(
    challenge: StreakChallenge,
    participant: StreakParticipant,
    question: StreakQuestion,
    *,
    participant_count: int,
    in_third_place_match: bool | None = None,
) -> tuple[str, str]:
    transition = streak_season_cutoff_at(challenge)
    if transition is None or question.closes_at < transition:
        return ("streak", "Streak")

    if participant_in_knockout_bracket_at(participant, question.closes_at):
        phase = knockout_phase_for_closes_at(
            challenge, question.closes_at, participant_count
        )
        stage = phase["label"] if phase else "Knockout"
        starts_at = phase["starts_at"] if phase else question.closes_at
        section_key = f"knockout:{starts_at.isoformat()}"
        # Final and 3rd place share the last knockout stage window; label by match.
        if (
            phase is not None
            and phase["round_index"] == knockout_total_rounds(participant_count)
            and (
                in_third_place_match
                if in_third_place_match is not None
                else _participant_in_third_place_match(challenge, participant)
            )
        ):
            stage = "3rd Place Match"
            section_key = f"{section_key}:third"
        return (section_key, f"Knockout: {stage}")

    return ("consolation", "Consolation")


def _win_loss_bundle(wins: int, losses: int) -> dict[str, int | str]:
    answered = wins + losses
    rate = wins / answered if answered else 0.0
    return {
        "wins": wins,
        "losses": losses,
        "record": f"{wins}-{losses}",
        "win_pct": round(rate * 100),
    }


def _leaderboard_entry(p: StreakParticipant, rank: int) -> dict[str, Any]:
    answered = p.wins + p.losses
    rate = p.wins / answered if answered else 0.0
    if p.streak_challenge.is_knockout:
        season_wins = p.frozen_wins
        season_losses = p.frozen_losses
        knockout_wins = p.wins - season_wins - p.consolation_wins
        knockout_losses = p.losses - season_losses - p.consolation_losses
        consolation_wins = p.consolation_wins
        consolation_losses = p.consolation_losses
    else:
        season_wins = p.wins
        season_losses = p.losses
        knockout_wins = 0
        knockout_losses = 0
        consolation_wins = 0
        consolation_losses = 0
    season_answered = season_wins + season_losses
    season_rate = season_wins / season_answered if season_answered else 0.0
    streak_signed = season_streak_signed(p)
    best_win_streak = season_best_win_streak(p)
    best_loss_streak = season_best_loss_streak(p)
    broken_win_streak = season_broken_win_streak(p)
    streak_bundle = _win_loss_bundle(season_wins, season_losses)
    knockout_bundle = _win_loss_bundle(knockout_wins, knockout_losses)
    consolation_bundle = _win_loss_bundle(consolation_wins, consolation_losses)
    total_bundle = _win_loss_bundle(p.wins, p.losses)
    return {
        "rank": rank,
        "user_id": p.user_id,
        "username": p.user.username,
        "display_name": streak_participant_label(p),
        "streak_signed": streak_signed,
        "current_display": serializers.streak_display(streak_signed),
        "long_win_display": _long_streak_display(best_win_streak, kind="win"),
        "long_loss_display": _long_streak_display(best_loss_streak, kind="loss"),
        "wins": p.wins,
        "losses": p.losses,
        "record": f"{p.wins}-{p.losses}",
        "win_pct": round(rate * 100),
        "season_wins": season_wins,
        "season_losses": season_losses,
        "season_record": streak_bundle["record"],
        "season_win_pct": streak_bundle["win_pct"],
        "streak_wins": season_wins,
        "streak_losses": season_losses,
        "streak_record": streak_bundle["record"],
        "streak_win_pct": streak_bundle["win_pct"],
        "knockout_wins": knockout_wins,
        "knockout_losses": knockout_losses,
        "knockout_record": knockout_bundle["record"],
        "knockout_win_pct": knockout_bundle["win_pct"],
        "consolation_wins": consolation_wins,
        "consolation_losses": consolation_losses,
        "consolation_record": consolation_bundle["record"],
        "consolation_win_pct": consolation_bundle["win_pct"],
        "total_wins": p.wins,
        "total_losses": p.losses,
        "total_record": total_bundle["record"],
        "total_win_pct": total_bundle["win_pct"],
        "best_win_streak": best_win_streak,
        "best_loss_streak": best_loss_streak,
        "broken_win_streak": broken_win_streak,
        "streak_display": serializers.streak_display(streak_signed),
        "win_rate": round(rate, 4),
    }


def _require_staff(user) -> JsonResponse | None:
    if not user.is_staff:
        return _json_error("Forbidden", 403)
    return None


def _schema_out_of_date_error(exc: DatabaseError) -> JsonResponse | None:
    message = str(exc).lower()
    if "streakquestionchoice" in message or "correct_choice" in message:
        return _json_error(
            "Database migration required. Run manage.py migrate, then restart the server.",
            503,
        )
    return None


@require_http_methods(["GET", "POST"])
def streak_competitions_list_create(request: HttpRequest) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    if request.method == "POST":
        denied = _require_staff(user)
        if denied is not None:
            return denied

        image_file = None
        if _is_multipart(request):
            post, files = _multipart_post_files(request)
            name = (post.get("name") or "").strip()
            image_file = files.get("image")
        else:
            try:
                body = _parse_json(request)
            except json.JSONDecodeError:
                return _json_error("Invalid JSON body", 400)
            name = (body.get("name") or "").strip()

        if not name:
            return _json_error("name is required", 400)

        competition = StreakCompetition.objects.create(name=name)
        if image_file:
            competition.image = image_file
            competition.save(update_fields=["image"])
        return JsonResponse(
            {"streak_competition": _competition_public(competition)},
            status=201,
        )

    rows = [
        _competition_public(c)
        for c in StreakCompetition.objects.annotate(
            challenge_count=Count("challenges")
        ).order_by("-created_at")
    ]
    return JsonResponse({"streak_competitions": rows})


def _pick_counts_by_question(question_ids: list[int]) -> dict[int, int]:
    """Total picks per question across all linked streak challenges."""
    if not question_ids:
        return {}
    rows = (
        StreakPick.objects.filter(question_id__in=question_ids)
        .values("question_id")
        .annotate(count=Count("id"))
    )
    return {row["question_id"]: row["count"] for row in rows}


def _question_admin(
    q: StreakQuestion, *, pick_count: int | None = None
) -> dict[str, Any]:
    correct_label = q.correct_choice.label if q.correct_choice_id else None
    if pick_count is None:
        pick_count = StreakPick.objects.filter(question_id=q.id).count()
    return {
        "id": q.id,
        "text": q.text,
        "closes_at": q.closes_at.isoformat(),
        "resolved_at": q.resolved_at.isoformat() if q.resolved_at else None,
        "choices": _choices_payload(q),
        "correct_choice_id": q.correct_choice_id,
        "correct_answer": correct_label,
        "order": q.order,
        "is_open": q.resolved_at is None,
        "pick_count": pick_count,
        "knockout_only": q.knockout_only,
    }


def _parse_choice_labels(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    labels: list[str] = []
    seen: set[str] = set()
    for item in raw:
        label = str(item).strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def _parse_choice_updates(raw: Any) -> list[tuple[int | None, str]] | None:
    """Parse PATCH/POST choice rows: id+label objects or plain label strings."""
    if not isinstance(raw, list):
        return None
    updates: list[tuple[int | None, str]] = []
    seen: set[str] = set()
    for item in raw:
        choice_id: int | None = None
        if isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            id_raw = item.get("id")
            if id_raw is not None:
                try:
                    choice_id = int(id_raw)
                except (TypeError, ValueError):
                    return None
        else:
            label = str(item).strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        updates.append((choice_id, label))
    return updates


def _sync_question_choices(
    question: StreakQuestion, updates: list[tuple[int | None, str]]
) -> None:
    if len(updates) < 2:
        raise ValueError("At least 2 choices are required")
    if len(updates) > 12:
        raise ValueError("No more than 12 choices allowed")

    existing = {c.id: c for c in question.choices.all()}
    keep_ids: set[int] = set()

    for order, (choice_id, label) in enumerate(updates, start=1):
        if choice_id is not None:
            choice = existing.get(choice_id)
            if choice is None or choice.question_id != question.id:
                raise ValueError("Unknown answer choice")
            if choice.label != label or choice.order != order:
                choice.label = label
                choice.order = order
                choice.save(update_fields=["label", "order"])
            keep_ids.add(choice_id)
        else:
            created = StreakQuestionChoice.objects.create(
                question=question, label=label, order=order
            )
            keep_ids.add(created.id)

    for choice_id, choice in existing.items():
        if choice_id in keep_ids:
            continue
        if StreakPick.objects.filter(choice_id=choice_id).exists():
            raise ValueError(
                f"Cannot remove “{choice.label}” — players have already picked it."
            )
        if question.correct_choice_id == choice_id:
            raise ValueError(
                f"Cannot remove “{choice.label}” — it is the resolved answer."
            )
        choice.delete()


def _questions_queryset():
    return (
        StreakQuestion.objects.prefetch_related("choices")
        .select_related("correct_choice")
        .order_by("closes_at", "order", "id")
    )


def _renumber_competition_questions(competition: StreakCompetition) -> None:
    """Keep order 1..n aligned with close time (earliest first)."""
    for idx, question in enumerate(
        competition.questions.order_by("closes_at", "id"), start=1
    ):
        if question.order != idx:
            question.order = idx
            question.save(update_fields=["order"])


@require_http_methods(["GET", "PATCH", "DELETE"])
def streak_competition_detail(
    request: HttpRequest, streak_competition_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)
    denied = _require_staff(user)
    if denied is not None:
        return denied

    competition = get_object_or_404(StreakCompetition, pk=streak_competition_id)

    if request.method == "DELETE":
        if competition.challenges.exists():
            return _json_error("Cannot delete competition with existing challenges", 409)
        with transaction.atomic():
            competition.delete()
        return JsonResponse({"ok": True})

    if request.method == "PATCH":
        update_fields: list[str] = []

        if _is_multipart(request):
            post, files = _multipart_post_files(request)
            name = (post.get("name") or "").strip()
            if name:
                competition.name = name
                update_fields.append("name")
            image_file = files.get("image")
            if image_file:
                competition.image = image_file
                update_fields.append("image")
        else:
            try:
                body = _parse_json(request)
            except json.JSONDecodeError:
                return _json_error("Invalid JSON body", 400)

            name = (body.get("name") or "").strip()
            if name:
                competition.name = name
                update_fields.append("name")
            if body.get("end_competition") is True:
                if competition.ended_at is None:
                    competition.ended_at = timezone.now()
                    update_fields.append("ended_at")

        if not update_fields:
            return _json_error("No changes requested", 400)
        competition.save(update_fields=update_fields)
        return JsonResponse(
            {"streak_competition": _competition_public(competition)}
        )

    try:
        question_rows = list(
            _questions_queryset().filter(streak_competition=competition)
        )
        pick_counts = _pick_counts_by_question([q.id for q in question_rows])
        questions = [
            _question_admin(q, pick_count=pick_counts.get(q.id, 0))
            for q in question_rows
        ]
    except DatabaseError as exc:
        schema_err = _schema_out_of_date_error(exc)
        if schema_err is not None:
            return schema_err
        raise
    return JsonResponse(
        {
            "streak_competition": _competition_public(competition),
            "questions": questions,
        }
    )


@require_http_methods(["POST"])
def streak_competition_question_create(
    request: HttpRequest, streak_competition_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)
    denied = _require_staff(user)
    if denied is not None:
        return denied

    competition = get_object_or_404(StreakCompetition, pk=streak_competition_id)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    text = (body.get("text") or "").strip()
    if not text:
        return _json_error("text is required", 400)

    closes_raw = body.get("closes_at")
    if not closes_raw:
        return _json_error("closes_at is required", 400)

    from brackets.utils.challenge_deadline import parse_deadline_est

    try:
        closes_at = parse_deadline_est(str(closes_raw))
    except ValueError:
        return _json_error("Invalid closes_at", 400)

    labels = _parse_choice_labels(body.get("choices"))
    if not labels or len(labels) < 2:
        return _json_error("At least 2 choices are required", 400)
    if len(labels) > 12:
        return _json_error("No more than 12 choices allowed", 400)

    try:
        with transaction.atomic():
            question = StreakQuestion.objects.create(
                streak_competition=competition,
                text=text,
                closes_at=closes_at,
                order=0,
                knockout_only=bool(body.get("knockout_only")),
            )
            for idx, label in enumerate(labels, start=1):
                StreakQuestionChoice.objects.create(
                    question=question, label=label, order=idx
                )
            _renumber_competition_questions(competition)
    except DatabaseError as exc:
        schema_err = _schema_out_of_date_error(exc)
        if schema_err is not None:
            return schema_err
        raise

    question = _questions_queryset().get(pk=question.pk)
    return JsonResponse({"question": _question_admin(question)}, status=201)


@require_http_methods(["GET", "POST"])
def streak_challenges_list_create(request: HttpRequest) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    if request.method == "POST":
        try:
            body = _parse_json(request)
        except json.JSONDecodeError:
            return _json_error("Invalid JSON body", 400)

        name = (body.get("name") or "").strip()
        if not name:
            return _json_error("name is required", 400)

        competition_id_raw = body.get("streak_competition_id")
        if competition_id_raw is None:
            return _json_error("streak_competition_id is required", 400)
        competition = StreakCompetition.objects.filter(
            pk=int(competition_id_raw)
        ).first()
        if competition is None:
            return _json_error("Streak competition not found", 404)

        is_private = bool(body.get("is_private"))
        join_code = _generate_join_code() if is_private else None

        with transaction.atomic():
            challenge = StreakChallenge.objects.create(
                name=name,
                streak_competition=competition,
                created_by=user,
                is_public=not is_private,
                join_code=join_code,
            )
            StreakParticipant.objects.create(
                streak_challenge=challenge,
                user=user,
                display_name=(user.username or "Host")[:80],
            )

        return JsonResponse(
            {"streak_challenge": _streak_summary(challenge, user)},
            status=201,
        )

    ids = StreakParticipant.objects.filter(user=user).values_list(
        "streak_challenge_id", flat=True
    )
    rows = [
        _streak_summary(c, user)
        for c in StreakChallenge.objects.filter(id__in=ids)
        .select_related("created_by", "streak_competition")
        .order_by("-created_at")
    ]
    return JsonResponse({"streak_challenges": rows})


@require_http_methods(["GET", "DELETE"])
def streak_challenge_detail(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(
        StreakChallenge.objects.select_related("streak_competition"),
        pk=streak_challenge_id,
    )

    if request.method == "DELETE":
        if challenge.created_by_id != user.id:
            return _json_error("Forbidden", 403)
        challenge.delete()
        return JsonResponse({"ok": True})

    participant = _streak_participant_or_none(challenge, user)
    process_scheduled_knockout(challenge)
    challenge.refresh_from_db()

    participant_count = StreakParticipant.objects.filter(
        streak_challenge=challenge
    ).count()
    deadline_picks = (
        open_deadline_pick_map(challenge.id, user.id, challenge=challenge)
        if participant
        else {}
    )
    question_rows = [
        q
        for q in _questions_queryset().filter(
            streak_competition_id=challenge.streak_competition_id
        )
        if question_visible_in_challenge(challenge, q)
    ]
    resolved_ids = [q.id for q in question_rows if q.resolved_at is not None]
    pick_stats_map = _pick_stats_by_question(challenge.id, resolved_ids)
    questions = [
        _question_public(
            q,
            user,
            challenge.id,
            challenge=challenge,
            deadline_picks=deadline_picks,
            pick_stats=pick_stats_map.get(q.id),
            participant_count=participant_count,
        )
        for q in question_rows
    ]
    return JsonResponse(
        {
            "streak_challenge": _streak_summary(
                challenge, user, participant=participant
            ),
            "questions": questions,
            "knockout_phases": knockout_phases_payload(challenge, participant_count),
        }
    )


@require_http_methods(["GET"])
def streak_challenge_leaderboard(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(StreakChallenge, pk=streak_challenge_id)
    if _streak_participant_or_none(challenge, user) is None:
        return _json_error("Forbidden", 403)

    if challenge.is_knockout:
        recalculate_streak_challenge(challenge.id)
        recalculate_consolation_for_challenge(challenge)

    participants = list(
        StreakParticipant.objects.filter(streak_challenge=challenge).select_related(
            "user",
            "streak_challenge",
        )
    )
    entries = [
        _leaderboard_entry(p, rank)
        for p, rank in streak_ranked_participants(participants)
    ]
    return JsonResponse({"entries": entries})


@require_http_methods(["GET"])
def streak_challenge_stats(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(StreakChallenge, pk=streak_challenge_id)
    if _streak_participant_or_none(challenge, user) is None:
        return _json_error("Forbidden", 403)

    from brackets.utils.streak_challenge_stats import get_streak_challenge_stats

    return JsonResponse(get_streak_challenge_stats(challenge))


@require_http_methods(["GET"])
def streak_challenge_awards(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(
        StreakChallenge.objects.select_related("streak_competition"),
        pk=streak_challenge_id,
    )
    if _streak_participant_or_none(challenge, user) is None:
        return _json_error("Forbidden", 403)

    competition = challenge.streak_competition
    if competition.ended_at is None:
        return _json_error("Competition is still active", 400)

    participants = list(
        StreakParticipant.objects.filter(streak_challenge=challenge).select_related(
            "user"
        )
    )
    return JsonResponse(compute_streak_awards(challenge, participants))


@require_http_methods(["GET"])
def streak_participant_picks(
    request: HttpRequest, streak_challenge_id: int, user_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(StreakChallenge, pk=streak_challenge_id)
    if _streak_participant_or_none(challenge, user) is None:
        return _json_error("Forbidden", 403)

    target = StreakParticipant.objects.filter(
        streak_challenge=challenge, user_id=user_id
    ).select_related("user", "streak_challenge").first()
    if target is None:
        return _json_error("Player not found", 404)

    participant_count = StreakParticipant.objects.filter(
        streak_challenge=challenge
    ).count()

    picks_qs = StreakPick.objects.filter(
        streak_challenge=challenge,
        user_id=user_id,
        question__resolved_at__isnull=False,
    )

    scope = (request.GET.get("scope") or "").strip().lower()
    if scope == "streak":
        if challenge.knockout_transition_at is not None:
            picks_qs = picks_qs.filter(
                question__closes_at__lt=challenge.knockout_transition_at
            )
    elif scope == "consolation":
        start = target.consolation_eligible_from or challenge.knockout_transition_at
        if start is None:
            picks_qs = picks_qs.none()
        else:
            picks_qs = picks_qs.filter(question__closes_at__gte=start)
    elif scope == "round":
        round_index_raw = request.GET.get("round_index")
        try:
            round_index = int(round_index_raw or "0")
        except ValueError:
            round_index = 0
        start = round_start_at(challenge, round_index)
        if start is None:
            picks_qs = picks_qs.none()
        else:
            picks_qs = picks_qs.filter(question__closes_at__gte=start)
            end = round_start_at(challenge, round_index + 1)
            if end is not None:
                picks_qs = picks_qs.filter(question__closes_at__lt=end)

    order_desc = scope in ("streak", "consolation", "round")
    picks = (
        picks_qs.select_related("question", "choice", "question__correct_choice")
        .prefetch_related("question__choices")
        .order_by(
            "-question__closes_at" if order_desc else "question__closes_at",
            "-question__order" if order_desc else "question__order",
            "-question__id" if order_desc else "question__id",
        )
    )
    in_third_place_match = _participant_in_third_place_match(challenge, target)
    rows = []
    for pick in picks:
        q = pick.question
        correct_label = (
            q.correct_choice.label if q.correct_choice_id else None
        )
        section_key, section_label = _participant_pick_section(
            challenge,
            target,
            q,
            participant_count=participant_count,
            in_third_place_match=in_third_place_match,
        )
        rows.append(
            {
                "question_id": q.id,
                "text": q.text,
                "closes_at": q.closes_at.isoformat(),
                "choices": _choices_payload(q),
                "pick_choice_id": pick.choice_id,
                "correct_choice_id": q.correct_choice_id,
                "pick_label": pick.choice.label,
                "correct_answer": correct_label,
                "is_correct": pick.choice_id == q.correct_choice_id,
                "section_key": section_key,
                "section_label": section_label,
            }
        )

    return JsonResponse(
        {
            "display_name": streak_participant_label(target),
            "username": target.user.username,
            "picks": rows,
        }
    )


@require_http_methods(["POST"])
def streak_challenges_join(request: HttpRequest) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    challenge_id_raw = body.get("streak_challenge_id")
    challenge = None
    if challenge_id_raw is not None:
        challenge = (
            StreakChallenge.objects.filter(pk=int(challenge_id_raw), is_public=True)
            .select_related("streak_competition", "created_by")
            .first()
        )
        if challenge is None:
            return _json_error("Streak challenge not found", 404)
    else:
        join_code = _normalize_join_code(body.get("join_code") or "")
        if join_code is None:
            return _json_error("join_code or streak_challenge_id is required", 400)
        challenge = (
            StreakChallenge.objects.filter(join_code=join_code)
            .select_related("streak_competition", "created_by")
            .first()
        )
        if challenge is None:
            return _json_error("Invalid join code", 404)

    display_name_raw = body.get("display_name")
    if display_name_raw is None or not str(display_name_raw).strip():
        return _json_error("display_name is required", 400)
    try:
        display_name = _normalize_display_name(str(display_name_raw))
    except ValueError as e:
        return _json_error(str(e), 400)

    participant, created = StreakParticipant.objects.get_or_create(
        streak_challenge=challenge,
        user=user,
        defaults={"display_name": display_name},
    )
    if not created and not (participant.display_name or "").strip():
        participant.display_name = display_name
        participant.save(update_fields=["display_name"])
    return JsonResponse({"streak_challenge": _streak_summary(challenge, user)})


def _streak_pick_context(request: HttpRequest, question_id: int):
    user = _require_user(request)
    if user is None:
        return None, _json_error("Authentication required", 401)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return None, _json_error("Invalid JSON body", 400)

    streak_challenge_id_raw = body.get("streak_challenge_id")
    if streak_challenge_id_raw is None:
        return None, _json_error("streak_challenge_id is required", 400)

    question = get_object_or_404(
        _questions_queryset().select_related("streak_competition"),
        pk=question_id,
    )
    challenge = get_object_or_404(
        StreakChallenge,
        pk=int(streak_challenge_id_raw),
        streak_competition_id=question.streak_competition_id,
    )
    try:
        _assert_streak_member(challenge, user)
    except PermissionError:
        return None, _json_error("Forbidden", 403)

    return (user, body, question, challenge), None


@require_http_methods(["POST", "DELETE"])
def streak_pick(request: HttpRequest, question_id: int) -> JsonResponse:
    ctx, err = _streak_pick_context(request, question_id)
    if err is not None:
        return err
    user, body, question, challenge = ctx

    if question.resolved_at is not None:
        return _json_error("This question is closed", 400)

    if question.closes_at <= timezone.now():
        return _json_error("This question is closed", 400)

    if question.streak_competition.ended_at is not None:
        return _json_error("This competition has ended", 400)

    if not question_visible_in_challenge(challenge, question):
        return _json_error("This question is not available in this challenge", 400)

    process_scheduled_knockout(challenge)
    challenge.refresh_from_db()

    participant_count = StreakParticipant.objects.filter(
        streak_challenge=challenge
    ).count()
    deadline_picks = open_deadline_pick_map(
        challenge.id, user.id, challenge=challenge
    )

    if request.method == "DELETE":
        StreakPick.objects.filter(
            streak_challenge=challenge,
            question=question,
            user=user,
        ).delete()
        deadline_picks = open_deadline_pick_map(
            challenge.id, user.id, challenge=challenge
        )
        question = _questions_queryset().get(pk=question.pk)
        return JsonResponse(
            {
                "question": _question_public(
                    question,
                    user,
                    challenge.id,
                    challenge=challenge,
                    deadline_picks=deadline_picks,
                    participant_count=participant_count,
                )
            }
        )

    choice_id_raw = body.get("choice_id")
    if choice_id_raw is None:
        return _json_error("choice_id is required", 400)
    try:
        choice_id = int(choice_id_raw)
    except (TypeError, ValueError):
        return _json_error("choice_id must be an integer", 400)

    choice = StreakQuestionChoice.objects.filter(
        pk=choice_id, question_id=question.id
    ).first()
    if choice is None:
        return _json_error("choice_id is invalid for this question", 400)

    if other_open_pick_at_same_deadline(challenge, user.id, question) is not None:
        return _json_error(
            "You already picked another question for this deadline. Clear that pick first.",
            409,
        )

    StreakPick.objects.update_or_create(
        streak_challenge=challenge,
        question=question,
        user=user,
        defaults={"choice": choice},
    )
    deadline_picks = open_deadline_pick_map(
        challenge.id, user.id, challenge=challenge
    )
    question = _questions_queryset().get(pk=question.pk)
    return JsonResponse(
        {
            "question": _question_public(
                question,
                user,
                challenge.id,
                challenge=challenge,
                deadline_picks=deadline_picks,
                participant_count=participant_count,
            )
        }
    )


@require_http_methods(["PATCH", "DELETE"])
def streak_question_detail(
    request: HttpRequest, question_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)
    denied = _require_staff(user)
    if denied is not None:
        return denied

    question = get_object_or_404(_questions_queryset(), pk=question_id)

    if request.method == "DELETE":
        competition_id = question.streak_competition_id
        question.delete()
        _renumber_competition_questions(
            StreakCompetition.objects.get(pk=competition_id)
        )
        return JsonResponse({"ok": True})

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    update_fields: list[str] = []

    if "text" in body:
        text = (body.get("text") or "").strip()
        if not text:
            return _json_error("text cannot be empty", 400)
        question.text = text
        update_fields.append("text")

    if "closes_at" in body:
        closes_raw = body.get("closes_at")
        if not closes_raw:
            return _json_error("closes_at cannot be empty", 400)
        from brackets.utils.challenge_deadline import parse_deadline_est

        try:
            question.closes_at = parse_deadline_est(str(closes_raw))
        except ValueError:
            return _json_error("Invalid closes_at", 400)
        update_fields.append("closes_at")

    if "knockout_only" in body:
        question.knockout_only = bool(body.get("knockout_only"))
        update_fields.append("knockout_only")

    choice_updates = None
    if "choices" in body:
        choice_updates = _parse_choice_updates(body.get("choices"))
        if choice_updates is None:
            return _json_error("choices must be a list of labels or {id, label} objects", 400)
        if not choice_updates:
            return _json_error("At least 2 choices are required", 400)

    if not update_fields and choice_updates is None:
        return _json_error("No fields to update", 400)

    try:
        with transaction.atomic():
            if update_fields:
                question.save(update_fields=update_fields)
            if choice_updates is not None:
                _sync_question_choices(question, choice_updates)
            if "closes_at" in update_fields:
                _renumber_competition_questions(question.streak_competition)
    except ValueError as e:
        return _json_error(str(e), 400)

    question = _questions_queryset().get(pk=question.pk)
    return JsonResponse({"question": _question_admin(question)})


@require_http_methods(["POST"])
def streak_question_resolve(
    request: HttpRequest, question_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)
    denied = _require_staff(user)
    if denied is not None:
        return denied

    question = get_object_or_404(_questions_queryset(), pk=question_id)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    if "correct_choice_id" not in body:
        return _json_error("correct_choice_id is required", 400)
    choice_id_raw = body.get("correct_choice_id")

    try:
        if choice_id_raw is None:
            clear_question_resolution(question)
        else:
            resolve_question(question, int(choice_id_raw))
    except (TypeError, ValueError):
        return _json_error("correct_choice_id must be an integer or null", 400)
    except ValueError as e:
        return _json_error(str(e), 400)

    question = _questions_queryset().get(pk=question.pk)
    return JsonResponse({"question": _question_admin(question)})


def _can_manage_knockout(challenge: StreakChallenge, user) -> bool:
    return challenge.created_by_id == user.id or user.is_staff


@require_http_methods(["PATCH"])
def streak_challenge_knockout_schedule(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(
        StreakChallenge.objects.select_related("streak_competition"),
        pk=streak_challenge_id,
    )
    if not _can_manage_knockout(challenge, user):
        return _json_error("Forbidden", 403)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    participant_count = StreakParticipant.objects.filter(
        streak_challenge=challenge
    ).count()

    if challenge.is_knockout:
        if "knockout_third_place_match" not in body:
            return _json_error("Knockout schedule is locked after knockout starts", 400)
        third_place_match = bool(body.get("knockout_third_place_match"))
        if third_place_match and not knockout_third_place_supported(participant_count):
            return _json_error(
                "Third place match requires at least four players in the bracket.",
                400,
            )
        if not knockout_third_place_setting_editable(challenge):
            return _json_error(
                "Third place match can no longer be changed after the semi-finals.",
                400,
            )
        challenge.knockout_third_place_match = third_place_match
        challenge.save(update_fields=["knockout_third_place_match"])
        participant = _streak_participant_or_none(challenge, user)
        return JsonResponse(
            {
                "streak_challenge": _streak_summary(
                    challenge, user, participant=participant
                ),
                "knockout_phases": knockout_phases_payload(
                    challenge, participant_count
                ),
            }
        )

    transition_raw = body.get("knockout_transition_at")
    if not transition_raw:
        return _json_error("knockout_transition_at is required", 400)

    from brackets.utils.challenge_deadline import parse_deadline_est

    try:
        transition_at = parse_deadline_est(str(transition_raw))
    except ValueError:
        return _json_error("Invalid knockout_transition_at", 400)

    round_starts_raw = body.get("knockout_round_starts")
    if round_starts_raw is None:
        round_starts: dict[str, str] = {}
    elif not isinstance(round_starts_raw, dict):
        return _json_error("knockout_round_starts must be an object", 400)
    else:
        round_starts = {str(k): str(v) for k, v in round_starts_raw.items() if v}

    round_headstart_raw = body.get("knockout_round_headstart")
    if round_headstart_raw is None:
        round_headstart: dict[str, bool] = {}
    elif not isinstance(round_headstart_raw, dict):
        return _json_error("knockout_round_headstart must be an object", 400)
    else:
        round_headstart = {
            str(k): bool(v) for k, v in round_headstart_raw.items()
        }

    if "knockout_third_place_match" in body:
        third_place_match = bool(body.get("knockout_third_place_match"))
    else:
        third_place_match = challenge.knockout_third_place_match

    if third_place_match and not knockout_third_place_supported(participant_count):
        return _json_error(
            "Third place match requires at least four players in the bracket.",
            400,
        )

    schedule_err = validate_knockout_schedule(
        challenge,
        transition_at=transition_at,
        round_starts=round_starts,
        participant_count=participant_count,
    )
    if schedule_err is not None:
        return _json_error(schedule_err, 400)

    challenge.knockout_transition_at = transition_at
    challenge.knockout_round_starts = round_starts
    challenge.knockout_round_headstart = round_headstart
    challenge.knockout_third_place_match = third_place_match
    challenge.save(
        update_fields=[
            "knockout_transition_at",
            "knockout_round_starts",
            "knockout_round_headstart",
            "knockout_third_place_match",
        ]
    )

    process_scheduled_knockout(challenge)
    challenge.refresh_from_db()

    participant = _streak_participant_or_none(challenge, user)
    return JsonResponse(
        {
            "streak_challenge": _streak_summary(
                challenge, user, participant=participant
            ),
            "knockout_phases": knockout_phases_payload(challenge, participant_count),
        }
    )


@require_http_methods(["GET"])
def streak_challenge_knockout(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(
        StreakChallenge.objects.select_related("streak_competition"),
        pk=streak_challenge_id,
    )
    if _streak_participant_or_none(challenge, user) is None:
        return _json_error("Forbidden", 403)
    process_scheduled_knockout(challenge)
    challenge.refresh_from_db()
    if not challenge.is_knockout:
        if challenge.knockout_transition_at is None:
            return _json_error("Challenge is not in knockout mode", 400)
        payload = projected_knockout_payload(challenge)
        if payload is None:
            return _json_error("Projected knockout unavailable", 400)
        return JsonResponse({"knockout": payload})

    from brackets.utils.streak_knockout import knockout_payload

    recalculate_consolation_for_challenge(challenge)
    payload = knockout_payload(challenge)
    if payload is None:
        return _json_error("Knockout not found", 404)
    payload["can_manage"] = _can_manage_knockout(challenge, user)
    return JsonResponse({"knockout": payload})


@require_http_methods(["POST"])
def streak_challenge_knockout_start(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(
        StreakChallenge.objects.select_related("streak_competition"),
        pk=streak_challenge_id,
    )
    if not _can_manage_knockout(challenge, user):
        return _json_error("Forbidden", 403)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    confirm = (body.get("confirm") or "").strip().lower()
    if confirm != "knockout":
        return _json_error('Type "knockout" to confirm', 400)

    from brackets.utils.streak_knockout import knockout_payload, start_knockout

    try:
        start_knockout(challenge)
    except ValueError as e:
        return _json_error(str(e), 400)

    challenge.refresh_from_db()
    payload = knockout_payload(challenge)
    if payload is not None:
        payload["can_manage"] = True
    return JsonResponse(
        {
            "streak_challenge": _streak_summary(challenge, user),
            "knockout": payload,
        }
    )


@require_http_methods(["PATCH"])
def streak_challenge_knockout_setup(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(StreakChallenge, pk=streak_challenge_id)
    if not _can_manage_knockout(challenge, user):
        return _json_error("Forbidden", 403)
    if not challenge.is_knockout:
        return _json_error("Challenge is not in knockout mode", 400)

    try:
        knockout = challenge.knockout
    except Exception:
        return _json_error("Knockout not found", 404)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    match_position = body.get("match_position")
    slot = body.get("slot")
    participant_id = body.get("participant_id")
    user_id = body.get("user_id")
    if match_position is None or slot is None:
        return _json_error("match_position and slot are required", 400)
    if participant_id is None and user_id is None:
        return _json_error("participant_id or user_id is required", 400)

    from brackets.utils.streak_knockout import knockout_payload, swap_round1_players

    if participant_id is None:
        p = StreakParticipant.objects.filter(
            streak_challenge=challenge, user_id=int(user_id)
        ).first()
        if p is None:
            return _json_error("Participant not found", 404)
        participant_id = p.id

    try:
        swap_round1_players(
            knockout,
            match_position=int(match_position),
            slot=str(slot),
            participant_id=int(participant_id),
        )
    except ValueError as e:
        return _json_error(str(e), 400)

    payload = knockout_payload(challenge)
    if payload is not None:
        payload["can_manage"] = True
    return JsonResponse({"knockout": payload})


@require_http_methods(["POST"])
def streak_challenge_knockout_advance(
    request: HttpRequest, streak_challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(StreakChallenge, pk=streak_challenge_id)
    if not _can_manage_knockout(challenge, user):
        return _json_error("Forbidden", 403)
    if not challenge.is_knockout:
        return _json_error("Challenge is not in knockout mode", 400)

    try:
        knockout = challenge.knockout
    except Exception:
        return _json_error("Knockout not found", 404)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        body = {}

    from brackets.utils.streak_knockout import advance_knockout_round, knockout_payload
    from brackets.utils.streak_knockout_rules import headstart_for_round

    headstart_enabled = body.get("headstart_enabled")
    if headstart_enabled is None:
        if knockout.status == StreakKnockout.Status.SETUP:
            headstart_enabled = headstart_for_round(challenge, 1)
        else:
            headstart_enabled = headstart_for_round(challenge, knockout.current_round + 1)
    elif isinstance(headstart_enabled, str):
        headstart_enabled = headstart_enabled.lower() in ("1", "true", "yes")
    else:
        headstart_enabled = bool(headstart_enabled)

    try:
        result = advance_knockout_round(
            knockout,
            headstart_enabled=bool(headstart_enabled),
        )
    except ValueError as e:
        return _json_error(str(e), 400)

    process_scheduled_knockout(challenge)
    challenge.refresh_from_db()

    payload = knockout_payload(challenge)
    if payload is not None:
        payload["can_manage"] = True
    return JsonResponse({"knockout": payload, **result})
