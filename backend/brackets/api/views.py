"""JSON API for brackets, user brackets, and matchup picks."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from brackets.models import Bracket, Matchup, UserBracket
from brackets.utils.knockout_tree import ensure_full_knockout_matchups

from . import serializers


def _json_error(message: str, status: int, code: str | None = None) -> JsonResponse:
    err: dict[str, Any] = {"message": message}
    if code:
        err["code"] = code
    return JsonResponse({"error": err}, status=status)


def _require_user(request: HttpRequest):
    if not request.user.is_authenticated:
        return None
    return request.user


def _parse_json(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    return json.loads(request.body)


@require_http_methods(["GET"])
def auth_me(request: HttpRequest) -> JsonResponse:
    if request.user.is_authenticated:
        return JsonResponse({"user": serializers.auth_user(request.user)})
    return JsonResponse({"user": None})


@require_http_methods(["POST"])
def auth_login(request: HttpRequest) -> JsonResponse:
    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        return _json_error("username and password required", 400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return _json_error("Invalid credentials", 401)

    login(request, user)
    return JsonResponse({"user": serializers.auth_user(user)})


@require_http_methods(["POST"])
def auth_logout(request: HttpRequest) -> JsonResponse:
    logout(request)
    return JsonResponse({"ok": True})


@require_http_methods(["GET"])
def brackets_list(request: HttpRequest) -> JsonResponse:
    rows = Bracket.objects.order_by("-created_at")[:100]
    return JsonResponse(
        {"brackets": [serializers.bracket_summary(b) for b in rows]}
    )


@require_http_methods(["GET"])
def bracket_detail(request: HttpRequest, bracket_id: int) -> JsonResponse:
    b = get_object_or_404(Bracket.objects.prefetch_related("stages"), pk=bracket_id)
    detail = serializers.bracket_detail(b)
    return JsonResponse({"bracket": detail})


@require_http_methods(["GET", "POST"])
def user_brackets_list_create(request: HttpRequest) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    if request.method == "GET":
        qs = UserBracket.objects.filter(user=user, is_master=False).select_related(
            "bracket"
        )
        bracket_id = request.GET.get("bracket_id")
        if bracket_id:
            qs = qs.filter(bracket_id=bracket_id)
        return JsonResponse(
            {
                "user_brackets": [
                    serializers.user_bracket_summary(ub) for ub in qs.order_by("-id")
                ]
            }
        )

    # POST
    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    bracket_id = body.get("bracket_id")
    if not bracket_id:
        return _json_error("bracket_id required", 400)

    get_object_or_404(Bracket, pk=bracket_id)
    challenge_id = body.get("challenge_id")

    try:
        ub = UserBracket.objects.create(
            user=user,
            bracket_id=bracket_id,
            challenge_id=challenge_id,
            is_master=False,
        )
    except IntegrityError:
        ub = UserBracket.objects.filter(
            user=user,
            bracket_id=bracket_id,
            challenge_id=challenge_id,
            is_master=False,
        ).first()
        if ub is None:
            return _json_error("Could not create or resolve user bracket", 409)

    try:
        ensure_full_knockout_matchups(ub)
    except ValueError as e:
        return _json_error(str(e), 400)

    return JsonResponse(
        {"user_bracket": serializers.user_bracket_detail(ub)},
        status=201,
    )


@require_http_methods(["GET"])
def user_bracket_detail(request: HttpRequest, user_bracket_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    ub = get_object_or_404(UserBracket, pk=user_bracket_id)
    if ub.user_id != user.id:
        return _json_error("Forbidden", 403)

    return JsonResponse({"user_bracket": serializers.user_bracket_detail(ub)})


@require_http_methods(["PATCH"])
def matchup_patch(request: HttpRequest, matchup_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    m = get_object_or_404(Matchup, pk=matchup_id)
    ub = m.user_bracket
    if ub.user_id != user.id:
        return _json_error("Forbidden", 403)
    if ub.is_master:
        return _json_error("Cannot edit master bracket via this API", 403)

    winner_id = body.get("winner_id")
    if winner_id is None:
        m.winner = None
        m.save()
        m.refresh_from_db()
        return JsonResponse({"matchup": serializers.matchup_public(m)})

    if m.contestant1_id != winner_id and m.contestant2_id != winner_id:
        return _json_error(
            "winner_id must match contestant1 or contestant2 in this matchup", 400
        )

    from brackets.models import BracketContestant

    m.winner = get_object_or_404(BracketContestant, pk=winner_id)
    m.save()
    m.refresh_from_db()
    return JsonResponse({"matchup": serializers.matchup_public(m)})
