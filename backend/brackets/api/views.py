"""JSON API for brackets, user brackets, and matchup picks."""

from __future__ import annotations

import json
import logging
import secrets
import string
from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from brackets.models import (
    Bracket,
    BracketChallenge,
    BracketContestant,
    BracketStage,
    BracketTemplate,
    ChallengeParticipant,
    Contestant,
    ContestantTag,
    Matchup,
    StreakCompetition,
    StreakQuestion,
    User,
    UserBracket,
    UserPick,
)
from brackets.utils.challenge_types import POLL, TOURNAMENT
from brackets.utils.knockout_rebuild import (
    clear_matchup_winner_and_downstream,
    remove_team_from_knockout_path,
)
from brackets.utils.bracket_admin_update import (
    apply_bracket_admin_fields,
    apply_stage_admin_patch,
)
from brackets.utils.bracket_factory import (
    VALID_STRUCTURE_TYPES,
    create_bracket_with_structure,
)
from brackets.utils.bracket_structure_config import (
    parse_bracket_metadata,
    parse_structure_config,
)
from brackets.utils.contestant_admin import (
    apply_contestant_admin_fields,
    parse_tag_ids,
    parse_tag_names,
    set_contestant_tags,
)
from brackets.utils.knockout_tree import (
    ensure_full_knockout_matchups,
    ensure_knockout_structure_for_user_bracket,
)
from brackets.utils.sync_group_knockout import sync_first_knockout_from_group_picks
from brackets.utils.tournament_teams import (
    apply_tournament_teams,
    tournament_team_capacity,
    tournament_teams_public,
)
from brackets.utils.bracket_completeness import user_bracket_is_complete
from brackets.utils.challenge_deadline import (
    assert_can_edit_picks,
    assert_can_join,
    deadline_passed,
    parse_deadline_est,
)
from brackets.utils.user_bracket_picks import merge_and_validate_user_bracket_metadata

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


def _staff_user_or_error(request: HttpRequest):
    user = _require_user(request)
    if user is None:
        return None, _json_error("Authentication required", 401)
    if not user.is_staff:
        return None, _json_error("Forbidden", 403)
    return user, None


def _try_sync_knockout_master(bracket: Bracket) -> None:
    try:
        from brackets.utils.leaderboard_scoring import on_master_bracket_changed
        from brackets.utils.challenge_stats import bump_challenge_stats_for_bracket
        from brackets.utils.sync_group_knockout import resync_group_knockout_for_bracket

        master = bracket.get_master_bracket()
        ensure_knockout_structure_for_user_bracket(master)
        if bracket.stages.filter(stage_type=BracketStage.StageType.GROUP).exists():
            resync_group_knockout_for_bracket(bracket)
        on_master_bracket_changed(bracket)
        bump_challenge_stats_for_bracket(bracket)
    except ValueError:
        pass


def _apply_bracket_contestant_rows(
    bracket: Bracket, rows: list[dict[str, Any]]
) -> None:
    for row in rows:
        cid = row.get("contestant_id")
        if cid is None:
            raise ValueError("Each entry needs contestant_id")
        try:
            cid_int = int(cid)
        except (TypeError, ValueError) as e:
            raise ValueError("contestant_id must be an integer") from e
        if not Contestant.objects.filter(pk=cid_int).exists():
            raise ValueError(f"Unknown contestant_id: {cid_int}")
        seed = row.get("seed")
        if seed is not None:
            try:
                seed = int(seed)
            except (TypeError, ValueError) as e:
                raise ValueError("seed must be an integer or null") from e
        BracketContestant.objects.update_or_create(
            bracket=bracket,
            contestant_id=cid_int,
            defaults={"seed": seed},
        )


def _parse_json(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    return json.loads(request.body)


def _is_multipart(request: HttpRequest) -> bool:
    return "multipart/form-data" in (request.content_type or "").lower()


def _multipart_post_files(request: HttpRequest):
    """
    POST and FILES for multipart requests.

    Django only auto-parses multipart bodies for POST. PATCH uploads (e.g. photo
    on edit) need an explicit parse.
    """
    if not _is_multipart(request):
        return request.POST, request.FILES
    if request.method == "POST" and (request.POST or request.FILES):
        return request.POST, request.FILES
    if request.POST or request.FILES:
        return request.POST, request.FILES
    from django.http.multipartparser import MultiPartParser, MultiPartParserError

    try:
        parser = MultiPartParser(
            request.META, request, request.upload_handlers
        )
        return parser.parse()
    except MultiPartParserError:
        return request.POST, request.FILES


def _validate_contestant_identifier(raw: str) -> str | None:
    ident = (raw or "").strip()
    if not ident:
        return None
    if " " in ident:
        return None
    if not all(ch.isalnum() or ch in "_-" for ch in ident):
        return None
    return ident


def _generate_join_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(32):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not BracketChallenge.objects.filter(join_code=code).exists():
            return code
    raise RuntimeError("Could not allocate join code")


def _normalize_join_code(raw: str) -> str | None:
    code = (raw or "").strip().upper()
    if not code:
        return None
    if len(code) > 8 or not code.isalnum():
        return None
    return code


def _next_available_bracket_identifier(raw_identifier: str) -> str:
    """
    Return a unique bracket identifier, adding numeric suffixes when needed.
    """
    base = (
        "".join(
            c if c.isalnum() or c in "-_" else "-" for c in (raw_identifier or "").lower()
        ).strip("-")[:48]
        or "tournament"
    )
    if not Bracket.objects.filter(identifier=base).exists():
        return base
    for n in range(2, 1000):
        suffix = f"-{n}"
        trimmed = base[: max(1, 48 - len(suffix))]
        candidate = f"{trimmed}{suffix}"
        if not Bracket.objects.filter(identifier=candidate).exists():
            return candidate
    raise ValueError("Could not allocate a unique bracket identifier.")


def _master_user_bracket_id_for_bracket(bracket_id: int) -> int | None:
    master = UserBracket.objects.filter(
        bracket_id=bracket_id, is_master=True
    ).first()
    return master.id if master else None


def _user_can_view_master_bracket(user, ub: UserBracket) -> bool:
    if not ub.is_master:
        return False
    if user.is_staff:
        return True
    if ChallengeParticipant.objects.filter(
        user=user,
        challenge__bracket_id=ub.bracket_id,
    ).exists():
        return True
    return BracketChallenge.objects.filter(
        bracket_id=ub.bracket_id,
        created_by=user,
    ).exists()


def _user_can_edit_master_bracket(user, ub: UserBracket) -> bool:
    if not ub.is_master:
        return False
    if user.is_staff:
        return True
    return BracketChallenge.objects.filter(
        bracket_id=ub.bracket_id,
        instance_type=TOURNAMENT,
        created_by=user,
    ).exists()


def _user_can_materialize_bracket_scores(user, bracket: Bracket) -> bool:
    if user.is_staff:
        return True
    return BracketChallenge.objects.filter(
        bracket_id=bracket.id,
        instance_type=TOURNAMENT,
        created_by=user,
    ).exists()


def _challenge_summary_for_user(
    challenge: BracketChallenge, user, request: HttpRequest | None = None
) -> dict[str, Any]:
    from brackets.utils.challenge_entries import user_entries_for_challenge

    ubs = list(user_entries_for_challenge(user, challenge))
    ub = ubs[0] if ubs else None
    is_participant = (
        bool(ubs)
        or ChallengeParticipant.objects.filter(
            challenge=challenge, user=user
        ).exists()
    )
    master_id = (
        _master_user_bracket_id_for_bracket(challenge.bracket_id)
        if is_participant
        else None
    )
    return serializers.challenge_summary(
        challenge,
        user=user,
        user_bracket_id=ub.id if ub else None,
        user_bracket=ub,
        user_entries=ubs,
        master_user_bracket_id=master_id,
        can_manage_bracket=_can_manage_bracket(user, challenge),
        request=request,
    )


def _can_manage_bracket(user, challenge: BracketChallenge) -> bool:
    return user.is_staff or (
        challenge.instance_type == TOURNAMENT
        and challenge.created_by_id == user.id
    )


def _can_edit_bracket_group_results_mode(user, bracket: Bracket) -> bool:
    return user.is_staff


def _normalize_display_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise ValueError("Display name is required.")
    if len(name) > 80:
        raise ValueError("Display name is too long (max 80 characters).")
    return name


def _user_can_view_challenge_bracket(viewer, ub: UserBracket) -> bool:
    if ub.is_master:
        return _user_can_view_master_bracket(viewer, ub)
    if ub.user_id == viewer.id:
        return True
    if ub.challenge_id is None:
        return False
    if not ChallengeParticipant.objects.filter(
        user=viewer,
        challenge_id=ub.challenge_id,
    ).exists():
        return False
    challenge = BracketChallenge.objects.filter(pk=ub.challenge_id).first()
    if challenge is None:
        return False
    from brackets.utils.challenge_entries import user_has_submitted_challenge

    return user_has_submitted_challenge(viewer, challenge)


def _enroll_user_in_challenge(
    user,
    challenge: BracketChallenge,
    *,
    display_name: str | None = None,
) -> UserBracket | None:
    """Add participant; create a user bracket when the activity type needs one."""
    from brackets.utils.challenge_entries import (
        assert_can_add_entry,
        assert_display_name_available,
        user_entry_count,
    )
    from brackets.utils.challenge_types import creates_user_bracket

    assert_can_join(challenge)
    ChallengeParticipant.objects.get_or_create(challenge=challenge, user=user)
    if not creates_user_bracket(challenge.instance_type):
        return None

    if display_name is not None:
        display_name = _normalize_display_name(display_name)

    if challenge.max_entries == 1 and user_entry_count(user, challenge) >= 1:
        ub = UserBracket.objects.filter(
            user=user, challenge=challenge, is_master=False
        ).first()
        assert ub is not None
        if display_name and not (ub.display_name or "").strip():
            assert_display_name_available(challenge, user, display_name)
            ub.display_name = display_name
            ub.save(update_fields=["display_name"])
        return ub

    assert_can_add_entry(user, challenge)
    if display_name is None:
        display_name = (user.username or "Player")[:80]
    assert_display_name_available(challenge, user, display_name)

    ub = UserBracket.objects.create(
        user=user,
        bracket=challenge.bracket,
        challenge=challenge,
        is_master=False,
        display_name=display_name,
    )
    ensure_knockout_structure_for_user_bracket(ub)
    return ub


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
def auth_register(request: HttpRequest) -> JsonResponse:
    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return _json_error("username and password required", 400)
    if len(username) > 150:
        return _json_error("username is too long", 400)
    if User.objects.filter(username__iexact=username).exists():
        return _json_error("That username is already taken", 409)

    try:
        validate_password(password)
    except ValidationError as exc:
        return _json_error(" ".join(exc.messages), 400)

    user = User.objects.create_user(username=username, password=password)
    login(request, user)
    return JsonResponse({"user": serializers.auth_user(user)}, status=201)


@require_http_methods(["POST"])
def auth_logout(request: HttpRequest) -> JsonResponse:
    logout(request)
    return JsonResponse({"ok": True})


@require_http_methods(["GET"])
def brackets_list(request: HttpRequest) -> JsonResponse:
    rows = (
        Bracket.objects.filter(is_reusable=True)
        .annotate(challenge_count=Count("bracketchallenge"))
        .order_by("-created_at")[:100]
    )
    return JsonResponse(
        {
            "brackets": [
                serializers.bracket_summary(b, request) for b in rows
            ]
        }
    )


@require_http_methods(["GET"])
def bracket_detail(request: HttpRequest, bracket_id: int) -> JsonResponse:
    b = get_object_or_404(Bracket.objects.prefetch_related("stages"), pk=bracket_id)
    master_id = None
    if request.user.is_authenticated and request.user.is_staff:
        master = UserBracket.objects.filter(bracket=b, is_master=True).first()
        if master:
            master_id = master.id
    detail = serializers.bracket_detail(
        b, master_user_bracket_id=master_id, request=request
    )
    return JsonResponse({"bracket": detail})


@require_http_methods(["PATCH"])
def bracket_group_results_mode(
    request: HttpRequest, bracket_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    bracket = get_object_or_404(Bracket.objects.prefetch_related("stages"), pk=bracket_id)
    if not _can_edit_bracket_group_results_mode(user, bracket):
        return _json_error("Forbidden", 403)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    from brackets.utils.group_results_mode import (
        VALID_GROUP_RESULTS_MODES,
        set_group_results_mode_on_metadata,
    )

    raw_mode = body.get("group_results_mode")
    if raw_mode not in VALID_GROUP_RESULTS_MODES:
        return _json_error("group_results_mode must be live or confirmed", 400)

    bracket.metadata = set_group_results_mode_on_metadata(bracket.metadata, raw_mode)
    with transaction.atomic():
        bracket.save(update_fields=["metadata"])
        from brackets.utils.leaderboard_scoring import on_master_bracket_changed
        from brackets.utils.challenge_stats import bump_challenge_stats_for_bracket

        on_master_bracket_changed(bracket, materialize=False)
        bump_challenge_stats_for_bracket(bracket)

    return JsonResponse(
        {"bracket": serializers.bracket_detail(bracket, request=request)}
    )


@require_http_methods(["POST"])
def bracket_materialize_scores(
    request: HttpRequest, bracket_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    bracket = get_object_or_404(Bracket, pk=bracket_id)
    if not _user_can_materialize_bracket_scores(user, bracket):
        return _json_error("Forbidden", 403)

    from brackets.utils.leaderboard_scoring import (
        is_master_scoring_pending,
        materialize_leaderboard_scores_for_bracket,
    )
    from brackets.utils.challenge_stats import bump_challenge_stats_for_bracket

    if not is_master_scoring_pending(bracket):
        return JsonResponse({"updated_count": 0, "leaderboard_scores_pending": False})

    updated_count = materialize_leaderboard_scores_for_bracket(bracket)
    bump_challenge_stats_for_bracket(bracket)
    return JsonResponse(
        {
            "updated_count": updated_count,
            "leaderboard_scores_pending": False,
        }
    )


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

    bracket = get_object_or_404(Bracket, pk=bracket_id)
    challenge_id = body.get("challenge_id")

    if challenge_id is not None:
        challenge = get_object_or_404(BracketChallenge, pk=int(challenge_id))
        if challenge.bracket_id != bracket.id:
            return _json_error("challenge does not belong to this bracket", 400)
        try:
            assert_can_join(challenge)
            raw_name = body.get("display_name")
            if raw_name is None or not str(raw_name).strip():
                return _json_error("display_name is required", 400)
            display_name = _normalize_display_name(str(raw_name))
            ub = _enroll_user_in_challenge(
                user, challenge, display_name=display_name
            )
        except ValueError as e:
            return _json_error(str(e), 400)
    else:
        try:
            ub = UserBracket.objects.create(
                user=user,
                bracket=bracket,
                challenge_id=None,
                is_master=False,
            )
        except IntegrityError:
            ub = UserBracket.objects.filter(
                user=user,
                bracket=bracket,
                challenge_id=None,
                is_master=False,
            ).first()
            if ub is None:
                return _json_error("Could not create or resolve user bracket", 409)

        try:
            ensure_knockout_structure_for_user_bracket(ub)
        except ValueError as e:
            return _json_error(str(e), 400)

    return JsonResponse(
        {"user_bracket": serializers.user_bracket_detail(ub, viewer=user)},
        status=201,
    )


@require_http_methods(["GET", "PATCH"])
def user_bracket_detail(request: HttpRequest, user_bracket_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    ub = get_object_or_404(UserBracket, pk=user_bracket_id)
    if ub.is_master:
        if request.method == "PATCH":
            if not _user_can_edit_master_bracket(user, ub):
                return _json_error("Forbidden", 403)
        elif not _user_can_view_master_bracket(user, ub):
            return _json_error("Forbidden", 403)
    elif not _user_can_view_challenge_bracket(user, ub):
        return _json_error("Forbidden", 403)
    elif request.method == "PATCH" and ub.user_id != user.id:
        return _json_error("Forbidden", 403)

    if request.method == "PATCH":
        try:
            assert_can_edit_picks(ub)
        except ValueError as e:
            return _json_error(str(e), 403)
        try:
            body = _parse_json(request)
        except json.JSONDecodeError:
            return _json_error("Invalid JSON body", 400)
        try:
            with transaction.atomic():
                ub.metadata = merge_and_validate_user_bracket_metadata(
                    ub.bracket, ub.metadata, body
                )
                ub.save(update_fields=["metadata"])
                sync_first_knockout_from_group_picks(ub)
        except ValueError as e:
            return _json_error(str(e), 400)
        from brackets.utils.leaderboard_scoring import (
            on_master_bracket_changed,
            refresh_user_bracket_leaderboard_cache,
        )
        from brackets.utils.challenge_stats import (
            invalidate_challenge_stats_for_user_bracket,
        )

        if ub.is_master:
            on_master_bracket_changed(ub.bracket, materialize=False)
        elif ub.submitted_at is not None:
            refresh_user_bracket_leaderboard_cache(ub)
        if ub.is_master or ub.submitted_at is not None:
            invalidate_challenge_stats_for_user_bracket(ub)
        return JsonResponse(
            {
                "user_bracket": serializers.user_bracket_detail(
                    ub, viewer=user
                )
            }
        )

    return JsonResponse(
        {"user_bracket": serializers.user_bracket_detail(ub, viewer=user)}
    )


@require_http_methods(["POST"])
def user_bracket_submit(request: HttpRequest, user_bracket_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    ub = get_object_or_404(UserBracket, pk=user_bracket_id)
    if ub.is_master or ub.user_id != user.id:
        return _json_error("Forbidden", 403)

    try:
        assert_can_edit_picks(ub)
    except ValueError as e:
        return _json_error(str(e), 403)

    complete, reason = user_bracket_is_complete(ub)
    if not complete:
        return _json_error(reason or "Bracket is incomplete", 400)

    ub.submitted_at = timezone.now()
    ub.save(update_fields=["submitted_at"])
    from brackets.utils.leaderboard_scoring import refresh_user_bracket_leaderboard_cache
    from brackets.utils.challenge_stats import invalidate_challenge_stats_for_user_bracket

    refresh_user_bracket_leaderboard_cache(ub)
    invalidate_challenge_stats_for_user_bracket(ub)
    return JsonResponse(
        {"user_bracket": serializers.user_bracket_detail(ub, viewer=user)}
    )


@require_http_methods(["GET", "POST"])
def challenges_list_create(request: HttpRequest) -> JsonResponse:
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

        from brackets.utils.challenge_types import (
            ALL_BRACKET_INSTANCE_TYPES,
            CHALLENGE,
            POLL,
            TOURNAMENT,
        )

        raw_type = (body.get("instance_type") or "CHALLENGE").strip().upper()
        if raw_type not in ALL_BRACKET_INSTANCE_TYPES:
            return _json_error(
                "instance_type must be CHALLENGE, TOURNAMENT, or POLL", 400
            )
        instance_type = raw_type

        is_private = bool(body.get("is_private"))
        is_public = not is_private

        submission_deadline = None
        if instance_type == CHALLENGE:
            deadline_raw = body.get("submission_deadline")
            if deadline_raw is not None and str(deadline_raw).strip():
                try:
                    submission_deadline = parse_deadline_est(str(deadline_raw))
                except ValueError:
                    return _json_error("Invalid submission_deadline", 400)

        bracket_id = body.get("bracket_id")
        if bracket_id:
            if instance_type in (TOURNAMENT, POLL):
                return _json_error(
                    "Tournaments and polls must create their own bracket.", 400
                )
            bracket = get_object_or_404(Bracket, pk=int(bracket_id))
            if not bracket.is_reusable:
                return _json_error(
                    "That bracket is not available for bracket challenges.", 400
                )
            bracket.ensure_master_bracket()
        elif instance_type in (TOURNAMENT, POLL):
            setup = body.get("bracket_setup")
            if not isinstance(setup, dict):
                return _json_error("bracket_setup is required", 400)
            structure = (setup.get("structure") or "SINGLE_ELIM").strip().upper()
            if structure not in VALID_STRUCTURE_TYPES:
                return _json_error(
                    "bracket_setup.structure must be SINGLE_ELIM or GROUP_KNOCKOUT",
                    400,
                )
            try:
                n = int(setup.get("number_of_contestants"))
            except (TypeError, ValueError):
                return _json_error(
                    "bracket_setup.number_of_contestants is required", 400
                )
            if n < 2:
                return _json_error("number_of_contestants must be at least 2", 400)
            if structure == "GROUP_KNOCKOUT" and n % 4 != 0:
                return _json_error(
                    "For group & knockout, number_of_contestants must be a multiple of 4",
                    400,
                )
            raw_id = (setup.get("identifier") or name).strip()
            try:
                identifier = _next_available_bracket_identifier(raw_id)
            except ValueError as e:
                return _json_error(str(e), 400)
            bracket_name = (setup.get("bracket_name") or name).strip()[:100]
            has_third = bool(setup.get("has_third_place"))
            try:
                structure_config = parse_structure_config(
                    setup.get("structure_config")
                )
            except ValueError as e:
                return _json_error(str(e), 400)
            try:
                bracket = create_bracket_with_structure(
                    structure,
                    identifier,
                    bracket_name,
                    n,
                    user,
                    has_third_place=has_third,
                    structure_config=structure_config,
                    is_reusable=False,
                )
            except ValueError as e:
                return _json_error(str(e), 400)
            except IntegrityError:
                return _json_error("That bracket identifier is already in use.", 409)
        else:
            return _json_error("bracket_id is required", 400)

        join_code = _generate_join_code() if is_private else None

        try:
            from brackets.utils.challenge_entries import normalize_max_entries

            max_entries = normalize_max_entries(
                body.get("max_entries", 1), instance_type=instance_type
            )
        except ValueError as e:
            return _json_error(str(e), 400)

        try:
            with transaction.atomic():
                challenge = BracketChallenge.objects.create(
                    name=name,
                    bracket=bracket,
                    instance_type=instance_type,
                    created_by=user,
                    is_public=is_public,
                    submission_deadline=submission_deadline,
                    join_code=join_code,
                    max_entries=max_entries,
                )
                _enroll_user_in_challenge(
                    user,
                    challenge,
                    display_name=(user.username or "Host")[:80],
                )
            if instance_type == TOURNAMENT:
                _try_sync_knockout_master(bracket)
        except IntegrityError:
            return _json_error("Could not create challenge", 409)
        except ValueError as e:
            return _json_error(str(e), 400)

        return JsonResponse(
            {
                "challenge": _challenge_summary_for_user(
                    challenge, user, request
                )
            },
            status=201,
        )

    from_participant = set(
        ChallengeParticipant.objects.filter(user=user).values_list(
            "challenge_id", flat=True
        )
    )
    from_brackets = set(
        UserBracket.objects.filter(
            user=user, is_master=False, challenge_id__isnull=False
        ).values_list("challenge_id", flat=True)
    )
    challenge_ids = from_participant | from_brackets
    if not challenge_ids:
        return JsonResponse({"challenges": []})

    challenges = list(
        BracketChallenge.objects.filter(id__in=challenge_ids).select_related(
            "bracket", "created_by"
        )
    )

    ubs_by_challenge: dict[int, list[UserBracket]] = {}
    for ub in UserBracket.objects.filter(
        user=user, is_master=False, challenge_id__in=challenge_ids
    ).order_by("-created_at"):
        ubs_by_challenge.setdefault(ub.challenge_id, []).append(ub)

    rows = []
    for c in sorted(challenges, key=lambda x: x.created_at, reverse=True):
        ubs = ubs_by_challenge.get(c.id, [])
        ub = ubs[0] if ubs else None
        is_participant = bool(ubs) or c.id in from_participant
        master_id = (
            _master_user_bracket_id_for_bracket(c.bracket_id)
            if is_participant
            else None
        )
        try:
            rows.append(
                serializers.challenge_summary(
                    c,
                    user=user,
                    user_bracket_id=ub.id if ub else None,
                    user_bracket=ub,
                    user_entries=ubs,
                    master_user_bracket_id=master_id,
                    can_manage_bracket=_can_manage_bracket(user, c),
                    request=request,
                )
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "challenge_summary failed for challenge %s", c.id
            )
    return JsonResponse({"challenges": rows})


@require_http_methods(["GET"])
def challenges_public_list(request: HttpRequest) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    from brackets.utils.challenge_types import CHALLENGE

    qs = (
        BracketChallenge.objects.filter(is_public=True)
        .select_related("bracket", "created_by")
        .order_by("-created_at")
    )
    challenges = [
        c
        for c in qs
        if not (c.instance_type == CHALLENGE and deadline_passed(c))
    ]

    rows = []
    for c in challenges:
        from brackets.utils.challenge_entries import user_entries_for_challenge

        ubs = list(user_entries_for_challenge(user, c))
        ub = ubs[0] if ubs else None
        is_participant = bool(ubs)
        master_id = (
            _master_user_bracket_id_for_bracket(c.bracket_id)
            if is_participant
            else None
        )
        rows.append(
            serializers.challenge_summary(
                c,
                user=user,
                user_bracket_id=ub.id if ub else None,
                user_bracket=ub,
                user_entries=ubs,
                master_user_bracket_id=master_id,
                can_manage_bracket=_can_manage_bracket(user, c),
                request=request,
            )
        )
    return JsonResponse({"challenges": rows})


@require_http_methods(["GET", "PATCH", "DELETE"])
def challenge_detail(request: HttpRequest, challenge_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(
        BracketChallenge.objects.select_related("bracket", "created_by"),
        pk=challenge_id,
    )

    if request.method == "DELETE":
        if challenge.created_by_id != user.id:
            return _json_error("Forbidden", 403)
        challenge.delete()
        return JsonResponse({"ok": True})

    if request.method == "PATCH":
        if challenge.created_by_id != user.id:
            return _json_error("Forbidden", 403)
        from brackets.utils.challenge_entries import (
            max_entries_in_use,
            normalize_max_entries,
        )
        from brackets.utils.challenge_types import CHALLENGE

        if challenge.instance_type != CHALLENGE:
            return _json_error(
                "Only bracket challenges support this setting", 400
            )
        try:
            body = _parse_json(request)
        except json.JSONDecodeError:
            return _json_error("Invalid JSON body", 400)
        if "max_entries" not in body:
            return _json_error("max_entries is required", 400)
        try:
            max_entries = normalize_max_entries(
                body.get("max_entries"), instance_type=CHALLENGE
            )
        except ValueError as e:
            return _json_error(str(e), 400)
        floor = max_entries_in_use(challenge)
        if max_entries < floor:
            label = "entry" if floor == 1 else "entries"
            return _json_error(
                f"At least one player already has {floor} {label}. "
                f"Set the limit to {floor} or higher.",
                400,
            )
        if max_entries != challenge.max_entries:
            challenge.max_entries = max_entries
            challenge.save(update_fields=["max_entries"])
        return JsonResponse(
            {"challenge": _challenge_summary_for_user(challenge, user, request)}
        )

    return JsonResponse(
        {"challenge": _challenge_summary_for_user(challenge, user, request)}
    )


@require_http_methods(["GET", "PUT"])
def challenge_teams(request: HttpRequest, challenge_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(
        BracketChallenge.objects.select_related("bracket"), pk=challenge_id
    )
    if challenge.instance_type != TOURNAMENT:
        return _json_error("Only tournaments support team setup", 400)
    if not _can_manage_bracket(user, challenge):
        return _json_error("Forbidden", 403)

    bracket = challenge.bracket
    if request.method == "GET":
        capacity = tournament_team_capacity(bracket)
        return JsonResponse(
            {
                "team_count": capacity,
                "teams": tournament_teams_public(bracket),
            }
        )

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    raw = body.get("teams")
    if not isinstance(raw, list):
        return _json_error("teams must be a list", 400)
    rows = [r for r in raw if isinstance(r, dict)]
    try:
        teams = apply_tournament_teams(bracket, rows)
    except ValueError as e:
        return _json_error(str(e), 400)

    return JsonResponse(
        {
            "team_count": tournament_team_capacity(bracket),
            "teams": teams,
        }
    )


@require_http_methods(["GET"])
def challenge_leaderboard(
    request: HttpRequest, challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    from brackets.utils.challenge_types import uses_prediction_scoring

    challenge = get_object_or_404(BracketChallenge, pk=challenge_id)
    if not ChallengeParticipant.objects.filter(
        challenge=challenge, user=user
    ).exists():
        ubs = UserBracket.objects.filter(challenge=challenge, is_master=False)
        if not ubs.filter(user=user).exists():
            return _json_error("Forbidden", 403)

    if not uses_prediction_scoring(challenge.instance_type):
        return JsonResponse({"columns": [], "entries": []})

    from brackets.utils.challenge_entries import user_has_submitted_challenge
    from brackets.utils.leaderboard_scoring import (
        get_master_scoring_revision,
        load_leaderboard_scoring_context,
        read_stored_leaderboard_scores,
    )
    from brackets.utils.top_four_picks import build_top_four_context, serialize_top_four_picks

    can_view_peers = user_has_submitted_challenge(user, challenge)
    hidden_top_four: list[None] = [None, None, None, None]

    bracket = challenge.bracket
    ctx = load_leaderboard_scoring_context(bracket)
    master = ctx.master
    stages = list(ctx.stages)
    scoring_revision = get_master_scoring_revision(bracket)
    top_four_ctx = build_top_four_context(bracket)
    columns = [
        serializers.leaderboard_column(key="potential", name="Potential"),
        serializers.leaderboard_column(key="top_four_picks", name="TOP 4 PICKS"),
    ]
    columns.extend(
        serializers.leaderboard_column(
            key=f"stage:{stage.id}",
            name=stage.name,
        )
        for stage in stages
    )
    columns.append(
        serializers.leaderboard_column(key="champion", name="Champions")
    )

    matchup_prefetch = Matchup.objects.select_related(
        "winner__contestant",
        "contestant1__contestant",
        "contestant2__contestant",
        "stage",
    )
    entries = []
    for ub in (
        UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            submitted_at__isnull=False,
        )
        .select_related("user", "bracket")
        .prefetch_related(
            Prefetch("matchup_set", queryset=matchup_prefetch),
        )
        .order_by("user__username")
    ):
        if master:
            scores = read_stored_leaderboard_scores(
                ub,
                revision=scoring_revision,
            )
            stage_scores = scores.stage_scores
            score = scores.score
            potential = scores.potential
        else:
            stage_scores = {col["key"]: None for col in columns}
            score = None
            potential = None
        player_name = (ub.display_name or "").strip() or ub.user.username
        entries.append(
            serializers.leaderboard_entry(
                username=ub.user.username,
                display_name=player_name,
                user_bracket_id=ub.id,
                score=score,
                potential=potential,
                stage_scores=stage_scores,
                top_four_picks=(
                    serialize_top_four_picks(ub, top_four_ctx)
                    if can_view_peers
                    else hidden_top_four
                ),
                submitted_at=ub.submitted_at,
            )
        )
    return JsonResponse({"columns": columns, "entries": entries})


@require_http_methods(["GET"])
def challenge_stats(request: HttpRequest, challenge_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    from brackets.utils.challenge_types import uses_prediction_scoring
    from brackets.utils.challenge_stats import get_challenge_stats

    challenge = get_object_or_404(
        BracketChallenge.objects.select_related("bracket"), pk=challenge_id
    )
    if not ChallengeParticipant.objects.filter(
        challenge=challenge, user=user
    ).exists():
        ubs = UserBracket.objects.filter(challenge=challenge, is_master=False)
        if not ubs.filter(user=user).exists():
            return _json_error("Forbidden", 403)

    if not uses_prediction_scoring(challenge.instance_type):
        return JsonResponse(
            {
                "submitted_count": 0,
                "group_stage": [],
                "knockout": {"columns": [], "rows": []},
            }
        )

    from brackets.utils.challenge_entries import user_has_submitted_challenge

    if not user_has_submitted_challenge(user, challenge):
        return _json_error("Submit your bracket to view stats.", 403)

    return JsonResponse(get_challenge_stats(challenge))


@require_http_methods(["POST"])
def challenges_join(request: HttpRequest) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    challenge_id_raw = body.get("challenge_id")
    challenge = None
    if challenge_id_raw is not None:
        challenge = BracketChallenge.objects.select_related("bracket").filter(
            pk=int(challenge_id_raw)
        ).first()
        if challenge is None:
            return _json_error("Challenge not found", 404)
        if not challenge.is_public and not ChallengeParticipant.objects.filter(
            challenge=challenge, user=user
        ).exists():
            return _json_error("This challenge is not public", 403)
    else:
        join_code = _normalize_join_code(body.get("join_code") or "")
        if join_code is None:
            return _json_error(
                "join_code or challenge_id is required", 400
            )
        challenge = (
            BracketChallenge.objects.select_related("bracket")
            .filter(join_code=join_code)
            .first()
        )
        if challenge is None:
            return _json_error("Invalid join code", 404)

    expected_type = body.get("instance_type")
    if expected_type is not None:
        expected = str(expected_type).strip().upper()
        if challenge.instance_type != expected:
            return _json_error("Join code does not match this activity type", 400)

    display_name_raw = body.get("display_name")
    if display_name_raw is None or not str(display_name_raw).strip():
        return _json_error("display_name is required", 400)
    try:
        display_name = _normalize_display_name(str(display_name_raw))
    except ValueError as e:
        return _json_error(str(e), 400)

    try:
        _enroll_user_in_challenge(user, challenge, display_name=display_name)
    except ValueError as e:
        return _json_error(str(e), 400)

    return JsonResponse(
        {"challenge": _challenge_summary_for_user(challenge, user, request)}
    )


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
    if ub.is_master:
        if not _user_can_edit_master_bracket(user, ub):
            return _json_error("Forbidden", 403)
    elif ub.user_id != user.id:
        return _json_error("Forbidden", 403)
    else:
        try:
            assert_can_edit_picks(ub)
        except ValueError as e:
            return _json_error(str(e), 403)

    winner_id = body.get("winner_id")
    if winner_id is None:
        clear_matchup_winner_and_downstream(m)
        m.refresh_from_db()
        from brackets.utils.leaderboard_scoring import (
            on_master_bracket_changed,
            refresh_user_bracket_leaderboard_cache,
        )
        from brackets.utils.challenge_stats import (
            invalidate_challenge_stats_for_user_bracket,
        )

        if ub.is_master:
            on_master_bracket_changed(ub.bracket, materialize=False)
        elif ub.submitted_at is not None:
            refresh_user_bracket_leaderboard_cache(ub)
        if ub.is_master or ub.submitted_at is not None:
            invalidate_challenge_stats_for_user_bracket(ub)
        return JsonResponse({"matchup": serializers.matchup_public(m)})

    if m.contestant1_id != winner_id and m.contestant2_id != winner_id:
        return _json_error(
            "winner_id must match contestant1 or contestant2 in this matchup", 400
        )

    old_winner_id = m.winner_id
    if old_winner_id and old_winner_id != winner_id:
        remove_team_from_knockout_path(m, old_winner_id)

    m.winner = get_object_or_404(BracketContestant, pk=winner_id)
    m.save()
    from brackets.utils.leaderboard_scoring import (
        on_master_bracket_changed,
        refresh_user_bracket_leaderboard_cache,
    )
    from brackets.utils.challenge_stats import invalidate_challenge_stats_for_user_bracket

    if ub.is_master:
        on_master_bracket_changed(ub.bracket, materialize=False)
    elif ub.submitted_at is not None:
        refresh_user_bracket_leaderboard_cache(ub)
    if ub.is_master or ub.submitted_at is not None:
        invalidate_challenge_stats_for_user_bracket(ub)
    if (
        not ub.is_master
        and ub.challenge_id is not None
        and ub.challenge.instance_type == POLL
    ):
        UserPick.objects.update_or_create(
            matchup=m,
            user=user,
            defaults={"selected_contestant_id": winner_id},
        )
    m.refresh_from_db()
    return JsonResponse({"matchup": serializers.matchup_public(m)})


@require_http_methods(["GET"])
def challenge_poll_votes(
    request: HttpRequest, challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(BracketChallenge, pk=challenge_id)
    if challenge.instance_type != POLL:
        return _json_error("Not a poll", 400)
    if not ChallengeParticipant.objects.filter(
        challenge=challenge, user=user
    ).exists():
        return _json_error("Forbidden", 403)

    try:
        stage_id = int(request.GET.get("stage_id", ""))
        position = int(request.GET.get("position", ""))
    except (TypeError, ValueError):
        return _json_error("stage_id and position are required", 400)

    user_ub = UserBracket.objects.filter(
        user=user, challenge=challenge, is_master=False
    ).first()
    user_picked = False
    if user_ub:
        user_picked = user_ub.matchup_set.filter(
            stage_id=stage_id,
            position=position,
            winner_id__isnull=False,
        ).exists()

    if not user_picked:
        return JsonResponse(
            {
                "user_picked": False,
                "totals": {},
                "total_votes": 0,
            }
        )

    matchup_ids = list(
        UserBracket.objects.filter(challenge=challenge, is_master=False)
        .values_list("id", flat=True)
    )
    matchups = Matchup.objects.filter(
        user_bracket_id__in=matchup_ids,
        stage_id=stage_id,
        position=position,
        winner_id__isnull=False,
    )
    totals: dict[str, int] = {}
    for mid, winner_id in matchups.values_list("id", "winner_id"):
        if winner_id is None:
            continue
        key = str(winner_id)
        totals[key] = totals.get(key, 0) + 1

    return JsonResponse(
        {
            "user_picked": True,
            "totals": totals,
            "total_votes": sum(totals.values()),
        }
    )


@require_http_methods(["GET", "POST"])
def admin_contestants_list_create(request: HttpRequest) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err

    if request.method == "GET":
        qs = Contestant.objects.prefetch_related("tags").order_by("-id")[:300]
        all_tags = [
            serializers.contestant_tag_public(t)
            for t in ContestantTag.objects.order_by("name")
        ]
        return JsonResponse(
            {
                "contestants": [
                    serializers.contestant_catalog(c, request) for c in qs
                ],
                "tags": all_tags,
            }
        )

    if _is_multipart(request):
        post, files = _multipart_post_files(request)
        identifier = _validate_contestant_identifier(post.get("identifier") or "")
        if not identifier:
            return _json_error(
                "identifier is required (letters, numbers, _ and - only; no spaces)",
                400,
            )
        name = (post.get("name") or "").strip()
        if not name:
            return _json_error("name is required", 400)
        description = (post.get("description") or "").strip()
        photo = files.get("photo")
        image_url = (post.get("image_url") or "").strip()
        metadata_raw = post.get("metadata")
        metadata = None
        if metadata_raw is not None and str(metadata_raw).strip():
            try:
                metadata = parse_bracket_metadata(metadata_raw)
            except ValueError as e:
                return _json_error(str(e), 400)
        try:
            c = Contestant.objects.create(
                identifier=identifier,
                name=name,
                description=description,
                created_by=user,
                photo=photo if photo else None,
                image_url=image_url,
                metadata=metadata,
            )
            if "tag_ids" in post or "tag_names" in post:
                set_contestant_tags(
                    c,
                    tag_ids=parse_tag_ids(post.get("tag_ids")),
                    tag_names=parse_tag_names(post.get("tag_names")),
                )
        except IntegrityError:
            return _json_error("That identifier is already in use.", 409)
        except (ValueError, json.JSONDecodeError) as e:
            return _json_error(str(e), 400)
        c = Contestant.objects.prefetch_related("tags").get(pk=c.pk)
        return JsonResponse(
            {"contestant": serializers.contestant_catalog(c, request)},
            status=201,
        )

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    identifier = _validate_contestant_identifier(body.get("identifier") or "")
    if not identifier:
        return _json_error(
            "identifier is required (letters, numbers, _ and - only; no spaces)",
            400,
        )
    name = (body.get("name") or "").strip()
    if not name:
        return _json_error("name is required", 400)

    description = (body.get("description") or "").strip()
    image_url = str(body.get("image_url") or "").strip()
    try:
        metadata = (
            parse_bracket_metadata(body.get("metadata"))
            if "metadata" in body
            else None
        )
    except ValueError as e:
        return _json_error(str(e), 400)

    try:
        c = Contestant.objects.create(
            identifier=identifier,
            name=name,
            description=description,
            created_by=user,
            image_url=image_url,
            metadata=metadata,
        )
        if "tag_ids" in body or "tag_names" in body:
            set_contestant_tags(
                c,
                tag_ids=parse_tag_ids(body.get("tag_ids")),
                tag_names=parse_tag_names(body.get("tag_names")),
            )
    except IntegrityError:
        return _json_error("That identifier is already in use.", 409)
    except (ValueError, json.JSONDecodeError) as e:
        return _json_error(str(e), 400)
    c = Contestant.objects.prefetch_related("tags").get(pk=c.pk)
    return JsonResponse(
        {"contestant": serializers.contestant_catalog(c, request)},
        status=201,
    )


@require_http_methods(["PATCH", "DELETE"])
def admin_contestant_detail(
    request: HttpRequest, contestant_id: int
) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err

    c = get_object_or_404(
        Contestant.objects.prefetch_related("tags"), pk=contestant_id
    )

    if request.method == "DELETE":
        c.delete()
        return JsonResponse({"ok": True})

    if _is_multipart(request):
        post, files = _multipart_post_files(request)
        name = (post.get("name") or "").strip()
        if name:
            c.name = name
        if "description" in post:
            c.description = (post.get("description") or "").strip()
        photo = files.get("photo")
        if photo:
            c.photo = photo
        admin_body: dict[str, Any] = {}
        if "image_url" in post:
            admin_body["image_url"] = post.get("image_url")
        if "metadata" in post:
            raw = post.get("metadata")
            if raw:
                try:
                    admin_body["metadata"] = json.loads(raw)
                except json.JSONDecodeError:
                    return _json_error("metadata must be valid JSON", 400)
            else:
                admin_body["metadata"] = None
        if "tag_ids" in post:
            admin_body["tag_ids"] = post.get("tag_ids")
        if "tag_names" in post:
            admin_body["tag_names"] = post.get("tag_names")
        save_fields: list[str] = []
        if name:
            save_fields.append("name")
        if "description" in post:
            save_fields.append("description")
        if photo:
            save_fields.append("photo")
        try:
            save_fields.extend(apply_contestant_admin_fields(c, admin_body))
            if save_fields:
                c.save(update_fields=list(dict.fromkeys(save_fields)))
        except ValueError as e:
            return _json_error(str(e), 400)
        c = Contestant.objects.prefetch_related("tags").get(pk=c.pk)
        return JsonResponse(
            {"contestant": serializers.contestant_catalog(c, request)}
        )

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    name = body.get("name")
    if name is not None:
        name = str(name).strip()
        if not name:
            return _json_error("name cannot be empty", 400)
        c.name = name

    if "description" in body:
        c.description = str(body.get("description") or "").strip()

    try:
        fields = apply_contestant_admin_fields(c, body)
        if name is not None:
            fields.append("name")
        if "description" in body:
            fields.append("description")
        if fields:
            c.save(update_fields=list(dict.fromkeys(fields)))
    except ValueError as e:
        return _json_error(str(e), 400)

    c = Contestant.objects.prefetch_related("tags").get(pk=c.pk)
    return JsonResponse(
        {"contestant": serializers.contestant_catalog(c, request)}
    )


@require_http_methods(["GET"])
def admin_delete_impact(
    request: HttpRequest, resource: str, object_id: int
) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err

    from brackets.utils.delete_impact import (
        bracket_delete_impact,
        contestant_delete_impact,
        streak_competition_delete_impact,
        streak_question_delete_impact,
    )

    handlers: dict[str, tuple[type, Any]] = {
        "bracket": (Bracket, bracket_delete_impact),
        "streak-competition": (StreakCompetition, streak_competition_delete_impact),
        "contestant": (Contestant, contestant_delete_impact),
        "streak-question": (StreakQuestion, streak_question_delete_impact),
    }
    entry = handlers.get(resource)
    if entry is None:
        return _json_error("Unknown resource", 404)

    model, impact_fn = entry
    obj = get_object_or_404(model, pk=object_id)
    return JsonResponse({"related": impact_fn(obj)})


def _bracket_templates_json() -> JsonResponse:
    rows = BracketTemplate.objects.order_by("-is_system", "name")
    return JsonResponse(
        {
            "templates": [
                serializers.bracket_template_summary(t) for t in rows
            ]
        }
    )


@require_http_methods(["GET"])
def bracket_templates_list(request: HttpRequest) -> JsonResponse:
    if _require_user(request) is None:
        return _json_error("Authentication required", 401)
    return _bracket_templates_json()


@require_http_methods(["GET"])
def admin_bracket_templates_list(request: HttpRequest) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err
    return _bracket_templates_json()


def _bool_request_field(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw or "").lower() in ("true", "1", "on", "yes")


@require_http_methods(["POST"])
def admin_brackets_create(request: HttpRequest) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err

    image_file = None
    if _is_multipart(request):
        post, files = _multipart_post_files(request)
        body = dict(post)
        raw_bc = body.get("bracket_contestants")
        if raw_bc:
            try:
                body["bracket_contestants"] = json.loads(raw_bc)
            except json.JSONDecodeError:
                return _json_error("bracket_contestants must be valid JSON", 400)
        raw_sc = body.get("structure_config")
        if raw_sc and isinstance(raw_sc, str):
            try:
                body["structure_config"] = json.loads(raw_sc)
            except json.JSONDecodeError:
                return _json_error("structure_config must be valid JSON", 400)
        raw_meta = body.get("metadata")
        if raw_meta and isinstance(raw_meta, str):
            try:
                body["metadata"] = json.loads(raw_meta)
            except json.JSONDecodeError:
                return _json_error("metadata must be valid JSON", 400)
        image_file = files.get("image")
    else:
        try:
            body = _parse_json(request)
        except json.JSONDecodeError:
            return _json_error("Invalid JSON body", 400)

    template_id = body.get("template_id")
    structure_raw = body.get("structure") or body.get("template_type")
    identifier = _validate_contestant_identifier(body.get("identifier") or "")
    if not identifier:
        return _json_error(
            "identifier is required (letters, numbers, _ and - only; no spaces)",
            400,
        )

    name = (body.get("name") or "").strip()
    if not name:
        return _json_error("name is required", 400)

    effective_type: str | None = None
    if template_id is not None:
        tpl = get_object_or_404(BracketTemplate, pk=int(template_id))
        effective_type = tpl.template_type
    elif structure_raw is not None:
        st = str(structure_raw).strip().upper()
        if st not in VALID_STRUCTURE_TYPES:
            return _json_error(
                "structure must be GROUP_KNOCKOUT or SINGLE_ELIM",
                400,
            )
        effective_type = st
    else:
        return _json_error(
            "Provide template_id or structure (GROUP_KNOCKOUT | SINGLE_ELIM)",
            400,
        )

    try:
        n = int(body.get("number_of_contestants"))
    except (TypeError, ValueError):
        return _json_error("number_of_contestants must be an integer", 400)

    if n < 2:
        return _json_error("number_of_contestants must be at least 2", 400)

    if effective_type == "GROUP_KNOCKOUT" and n % 4 != 0:
        return _json_error(
            "For group & knockout, number_of_contestants must be a multiple of 4",
            400,
        )

    has_third_place = _bool_request_field(body.get("has_third_place"))
    description = (body.get("description") or "").strip()

    try:
        structure_config = parse_structure_config(body.get("structure_config"))
        bracket_metadata = parse_bracket_metadata(body.get("metadata"))
    except ValueError as e:
        return _json_error(str(e), 400)

    show_seeds = True
    if "show_seeds" in body:
        show_seeds = _bool_request_field(body["show_seeds"])

    randomize = _bool_request_field(body.get("randomize_seeds_per_challenge"))

    raw_assign = body.get("bracket_contestants")
    assign_rows: list[dict[str, Any]] | None = None
    if raw_assign is not None:
        if not isinstance(raw_assign, list):
            return _json_error("bracket_contestants must be a list", 400)
        assign_rows = [r for r in raw_assign if isinstance(r, dict)]

    try:
        with transaction.atomic():
            bracket = create_bracket_with_structure(
                effective_type,
                identifier,
                name,
                n,
                user,
                has_third_place=has_third_place,
                show_seeds=show_seeds,
                metadata=bracket_metadata,
                randomize_seeds_per_challenge=randomize,
                structure_config=structure_config,
            )
            if description:
                bracket.description = description
                bracket.save(update_fields=["description"])

            if image_file:
                bracket.image = image_file
                bracket.save(update_fields=["image"])

            if assign_rows is not None:
                _apply_bracket_contestant_rows(bracket, assign_rows)
    except ValueError as e:
        return _json_error(str(e), 400)
    except IntegrityError:
        return _json_error("That identifier is already in use.", 409)

    _try_sync_knockout_master(bracket)
    bracket.refresh_from_db()
    b = get_object_or_404(
        Bracket.objects.prefetch_related("stages"), pk=bracket.pk
    )
    return JsonResponse(
        {"bracket": serializers.bracket_detail(b, request=request)},
        status=201,
    )


@require_http_methods(["POST"])
def admin_bracket_contestants_assign(
    request: HttpRequest, bracket_id: int
) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err

    bracket = get_object_or_404(Bracket, pk=bracket_id)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    raw = body.get("assignments")
    if not isinstance(raw, list):
        return _json_error("assignments must be a list", 400)
    rows = [r for r in raw if isinstance(r, dict)]
    try:
        with transaction.atomic():
            _apply_bracket_contestant_rows(bracket, rows)
    except ValueError as e:
        return _json_error(str(e), 400)

    _try_sync_knockout_master(bracket)
    b = get_object_or_404(
        Bracket.objects.prefetch_related("stages"), pk=bracket.pk
    )
    return JsonResponse({"bracket": serializers.bracket_detail(b)})


@require_http_methods(["PATCH", "DELETE"])
def admin_bracket_detail(
    request: HttpRequest, bracket_id: int
) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err

    bracket = get_object_or_404(Bracket, pk=bracket_id)

    if request.method == "DELETE":
        with transaction.atomic():
            bracket.delete()
        return JsonResponse({"ok": True})

    bracket_fields: list[str] = []

    if _is_multipart(request):
        post, files = _multipart_post_files(request)
        name = (post.get("name") or "").strip()
        if name:
            bracket.name = name
            bracket_fields.append("name")
        if "description" in post:
            bracket.description = (post.get("description") or "").strip()
            bracket_fields.append("description")
        image = files.get("image")
        if image:
            bracket.image = image
            bracket_fields.append("image")

        admin_body: dict[str, Any] = {}
        for key in (
            "show_seeds",
            "randomize_seeds_per_challenge",
            "has_third_place_match",
            "points_champion",
            "points_third_place_winner",
            "metadata",
        ):
            if key in post:
                raw = post.get(key)
                if key == "metadata" and raw:
                    try:
                        admin_body[key] = json.loads(raw)
                    except json.JSONDecodeError:
                        return _json_error("metadata must be valid JSON", 400)
                else:
                    admin_body[key] = raw
        bracket_fields.extend(apply_bracket_admin_fields(bracket, admin_body))
    else:
        try:
            body = _parse_json(request)
        except json.JSONDecodeError:
            return _json_error("Invalid JSON body", 400)

        name = body.get("name")
        if name is not None:
            name = str(name).strip()
            if not name:
                return _json_error("name cannot be empty", 400)
            bracket.name = name
            bracket_fields.append("name")

        if "description" in body:
            bracket.description = str(body.get("description") or "").strip()
            bracket_fields.append("description")

        try:
            bracket_fields.extend(apply_bracket_admin_fields(bracket, body))
        except ValueError as e:
            return _json_error(str(e), 400)

    if bracket_fields:
        unique_fields = list(dict.fromkeys(bracket_fields))
        with transaction.atomic():
            bracket.save(update_fields=unique_fields)
            if "has_third_place_match" in unique_fields:
                from brackets.utils.third_place_structure import (
                    sync_third_place_structure,
                )

                sync_third_place_structure(bracket)
            scoring_fields = {
                "points_champion",
                "points_third_place_winner",
                "has_third_place_match",
                "metadata",
            }
            if any(field in unique_fields for field in scoring_fields):
                from brackets.utils.leaderboard_scoring import (
                    on_master_bracket_changed,
                )
                from brackets.utils.challenge_stats import (
                    bump_challenge_stats_for_bracket,
                )

                on_master_bracket_changed(bracket)
                bump_challenge_stats_for_bracket(bracket)
    b = get_object_or_404(
        Bracket.objects.prefetch_related("stages"), pk=bracket.pk
    )
    return JsonResponse(
        {"bracket": serializers.bracket_detail(b, request=request)}
    )


@require_http_methods(["PATCH"])
def admin_bracket_stages_update(
    request: HttpRequest, bracket_id: int
) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err

    bracket = get_object_or_404(Bracket, pk=bracket_id)

    try:
        body = _parse_json(request)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    raw = body.get("stages")
    if not isinstance(raw, list):
        return _json_error("stages must be a list", 400)

    valid_ids = set(bracket.stages.values_list("id", flat=True))

    try:
        scoring_changed = False
        with transaction.atomic():
            for item in raw:
                if not isinstance(item, dict) or "id" not in item:
                    continue
                sid = int(item["id"])
                if sid not in valid_ids:
                    return _json_error(f"Unknown stage id {sid}", 400)
                stage = get_object_or_404(BracketStage, pk=sid, bracket=bracket)
                patch = {k: v for k, v in item.items() if k != "id"}
                fields = apply_stage_admin_patch(stage, patch)
                if fields:
                    stage.save(update_fields=fields)
                    scoring_changed = True
            if scoring_changed:
                from brackets.utils.leaderboard_scoring import (
                    on_master_bracket_changed,
                )
                from brackets.utils.challenge_stats import (
                    bump_challenge_stats_for_bracket,
                )

                on_master_bracket_changed(bracket)
                bump_challenge_stats_for_bracket(bracket)
    except ValueError as e:
        return _json_error(str(e), 400)

    b = get_object_or_404(
        Bracket.objects.prefetch_related("stages"), pk=bracket.pk
    )
    return JsonResponse(
        {"bracket": serializers.bracket_detail(b, request=request)}
    )
