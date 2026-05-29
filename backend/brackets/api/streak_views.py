"""Streak competition and challenge API."""

from __future__ import annotations

import json
from typing import Any

from django.db import DatabaseError, IntegrityError, transaction
from collections import defaultdict

from django.db.models import Count
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from brackets.api import serializers
from brackets.api.views import (
    _generate_join_code,
    _is_multipart,
    _json_error,
    _multipart_post_files,
    _normalize_join_code,
    _parse_json,
    _require_user,
)
from brackets.models import (
    StreakChallenge,
    StreakCompetition,
    StreakParticipant,
    StreakPick,
    StreakQuestion,
    StreakQuestionChoice,
)
from brackets.utils.leaderboard_preview import (
    streak_challenge_leaderboard_preview,
    streak_participant_sort_key,
)
from brackets.utils.streak_deadlines import (
    closes_at_key,
    open_deadline_pick_map,
    other_open_pick_at_same_deadline,
)
from brackets.utils.streak_scoring import (
    clear_question_resolution,
    recalculate_streak_competition,
    resolve_question,
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
        "streak_signed": participant.streak_signed if participant else 0,
        "streak_display": serializers.streak_display(
            participant.streak_signed if participant else 0
        ),
        "is_creator": c.created_by_id == user.id,
    }


def _pick_pct_by_question(
    streak_challenge_id: int, question_ids: list[int]
) -> dict[int, dict[int, int]]:
    """question_id -> choice_id -> whole-number percent of picks in this challenge."""
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
    result: dict[int, dict[int, int]] = {}
    for question_id, choice_counts in counts.items():
        total = sum(choice_counts.values())
        if total == 0:
            result[question_id] = {}
            continue
        result[question_id] = {
            choice_id: round(count * 100 / total)
            for choice_id, count in choice_counts.items()
        }
    return result


def _choices_payload(
    question: StreakQuestion,
    pick_pcts: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for choice in question.choices.all():
        item: dict[str, Any] = {"id": choice.id, "label": choice.label}
        if pick_pcts is not None:
            item["pick_pct"] = pick_pcts.get(choice.id, 0)
        rows.append(item)
    return rows


def _question_public(
    q: StreakQuestion,
    user,
    streak_challenge_id: int,
    *,
    deadline_picks: dict | None = None,
    pick_pcts: dict[int, int] | None = None,
) -> dict[str, Any]:
    pick = (
        StreakPick.objects.filter(
            question=q, user=user, streak_challenge_id=streak_challenge_id
        )
        .select_related("choice")
        .first()
    )
    correct_label = q.correct_choice.label if q.correct_choice_id else None
    is_open = q.resolved_at is None
    locked_by_question_id = None
    deadline_locked = False
    if is_open and deadline_picks is not None:
        locked_by_question_id = deadline_picks.get(closes_at_key(q.closes_at))
        deadline_locked = (
            locked_by_question_id is not None
            and locked_by_question_id != q.id
            and pick is None
        )
    return {
        "id": q.id,
        "text": q.text,
        "closes_at": q.closes_at.isoformat(),
        "resolved_at": q.resolved_at.isoformat() if q.resolved_at else None,
        "choices": _choices_payload(
            q, pick_pcts if q.resolved_at is not None else None
        ),
        "correct_choice_id": q.correct_choice_id,
        "correct_answer": correct_label,
        "user_choice_id": pick.choice_id if pick else None,
        "user_answer": pick.choice.label if pick else None,
        "is_open": is_open,
        "deadline_locked": deadline_locked,
        "locked_by_question_id": locked_by_question_id,
        "can_clear_pick": is_open and pick is not None,
    }


def _long_streak_display(value: int, *, kind: str) -> str:
    if value <= 0:
        return "—"
    if kind == "win":
        return serializers.streak_display(value)
    return f"{value}L"


def _leaderboard_entry(p: StreakParticipant, rank: int) -> dict[str, Any]:
    answered = p.wins + p.losses
    rate = p.wins / answered if answered else 0.0
    return {
        "rank": rank,
        "user_id": p.user_id,
        "username": p.user.username,
        "streak_signed": p.streak_signed,
        "current_display": serializers.streak_display(p.streak_signed),
        "long_win_display": _long_streak_display(p.best_win_streak, kind="win"),
        "long_loss_display": _long_streak_display(p.best_loss_streak, kind="loss"),
        "wins": p.wins,
        "losses": p.losses,
        "record": f"{p.wins}-{p.losses}",
        "win_pct": round(rate * 100),
        "streak_display": serializers.streak_display(p.streak_signed),
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


def _question_admin(q: StreakQuestion) -> dict[str, Any]:
    correct_label = q.correct_choice.label if q.correct_choice_id else None
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


def _questions_queryset():
    return StreakQuestion.objects.prefetch_related("choices").select_related(
        "correct_choice"
    )


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
            if not name:
                return _json_error("name is required", 400)
            competition.name = name
            update_fields.append("name")

        if not update_fields:
            return _json_error("name is required", 400)
        competition.save(update_fields=update_fields)
        return JsonResponse(
            {"streak_competition": _competition_public(competition)}
        )

    try:
        questions = [
            _question_admin(q)
            for q in _questions_queryset().filter(streak_competition=competition)
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

    order = competition.questions.count() + 1
    try:
        with transaction.atomic():
            question = StreakQuestion.objects.create(
                streak_competition=competition,
                text=text,
                closes_at=closes_at,
                order=order,
            )
            for idx, label in enumerate(labels, start=1):
                StreakQuestionChoice.objects.create(
                    question=question, label=label, order=idx
                )
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
            StreakParticipant.objects.create(streak_challenge=challenge, user=user)

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
    deadline_picks = (
        open_deadline_pick_map(challenge.id, user.id) if participant else {}
    )
    question_rows = list(
        _questions_queryset().filter(
            streak_competition_id=challenge.streak_competition_id
        )
    )
    resolved_ids = [q.id for q in question_rows if q.resolved_at is not None]
    pick_pct_map = _pick_pct_by_question(challenge.id, resolved_ids)
    questions = [
        _question_public(
            q,
            user,
            challenge.id,
            deadline_picks=deadline_picks,
            pick_pcts=pick_pct_map.get(q.id),
        )
        for q in question_rows
    ]
    return JsonResponse(
        {
            "streak_challenge": _streak_summary(
                challenge, user, participant=participant
            ),
            "questions": questions,
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

    participants = list(
        StreakParticipant.objects.filter(streak_challenge=challenge).select_related(
            "user"
        )
    )
    participants.sort(key=streak_participant_sort_key, reverse=True)
    entries = [
        _leaderboard_entry(p, rank) for rank, p in enumerate(participants, start=1)
    ]
    return JsonResponse({"entries": entries})


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
    ).select_related("user").first()
    if target is None:
        return _json_error("Player not found", 404)

    picks = (
        StreakPick.objects.filter(
            streak_challenge=challenge,
            user_id=user_id,
            question__resolved_at__isnull=False,
        )
        .select_related("question", "choice", "question__correct_choice")
        .prefetch_related("question__choices")
        .order_by("-question__closes_at", "-question__order", "-question__id")
    )
    rows = []
    for pick in picks:
        q = pick.question
        correct_label = (
            q.correct_choice.label if q.correct_choice_id else None
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
            }
        )

    return JsonResponse(
        {
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

    StreakParticipant.objects.get_or_create(streak_challenge=challenge, user=user)
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

    deadline_picks = open_deadline_pick_map(challenge.id, user.id)

    if request.method == "DELETE":
        StreakPick.objects.filter(
            streak_challenge=challenge,
            question=question,
            user=user,
        ).delete()
        deadline_picks = open_deadline_pick_map(challenge.id, user.id)
        question = _questions_queryset().get(pk=question.pk)
        return JsonResponse(
            {
                "question": _question_public(
                    question, user, challenge.id, deadline_picks=deadline_picks
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
    deadline_picks = open_deadline_pick_map(challenge.id, user.id)
    question = _questions_queryset().get(pk=question.pk)
    return JsonResponse(
        {
            "question": _question_public(
                question, user, challenge.id, deadline_picks=deadline_picks
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
        question.delete()
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

    if not update_fields:
        return _json_error("No fields to update", 400)

    question.save(update_fields=update_fields)
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
