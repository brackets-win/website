"""JSON API for brackets, user brackets, and matchup picks."""

from __future__ import annotations

import json
import secrets
import string
from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction
from django.db.models import Count
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
    UserBracket,
)
from brackets.utils.knockout_rebuild import (
    clear_matchup_winner_and_downstream,
    rebuild_knockout_from_first_round,
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
        master = bracket.get_master_bracket()
        ensure_knockout_structure_for_user_bracket(master)
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


def _challenge_summary_for_user(
    challenge: BracketChallenge, user, request: HttpRequest | None = None
) -> dict[str, Any]:
    ub = UserBracket.objects.filter(
        user=user, challenge=challenge, is_master=False
    ).first()
    return serializers.challenge_summary(
        challenge,
        user_bracket_id=ub.id if ub else None,
        user_bracket=ub,
        request=request,
    )


def _enroll_user_in_challenge(user, challenge: BracketChallenge) -> UserBracket:
    """Add participant row and user bracket for a challenge (idempotent)."""
    assert_can_join(challenge)
    ChallengeParticipant.objects.get_or_create(challenge=challenge, user=user)
    ub, _ = UserBracket.objects.get_or_create(
        user=user,
        bracket=challenge.bracket,
        challenge=challenge,
        is_master=False,
        defaults={},
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
def auth_logout(request: HttpRequest) -> JsonResponse:
    logout(request)
    return JsonResponse({"ok": True})


@require_http_methods(["GET"])
def brackets_list(request: HttpRequest) -> JsonResponse:
    rows = (
        Bracket.objects.annotate(challenge_count=Count("bracketchallenge"))
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
            ub = _enroll_user_in_challenge(user, challenge)
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
        {"user_bracket": serializers.user_bracket_detail(ub)},
        status=201,
    )


@require_http_methods(["GET", "PATCH"])
def user_bracket_detail(request: HttpRequest, user_bracket_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    ub = get_object_or_404(UserBracket, pk=user_bracket_id)
    if ub.is_master:
        if not user.is_staff:
            return _json_error("Forbidden", 403)
    elif ub.user_id != user.id:
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
                if not ub.is_master:
                    sync_first_knockout_from_group_picks(ub)
        except ValueError as e:
            return _json_error(str(e), 400)
        return JsonResponse({"user_bracket": serializers.user_bracket_detail(ub)})

    return JsonResponse({"user_bracket": serializers.user_bracket_detail(ub)})


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
    return JsonResponse({"user_bracket": serializers.user_bracket_detail(ub)})


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

        bracket_id = body.get("bracket_id")
        if not bracket_id:
            return _json_error("bracket_id is required", 400)

        bracket = get_object_or_404(Bracket, pk=int(bracket_id))
        instance_type = "CHALLENGE"

        is_private = bool(body.get("is_private"))
        is_public = not is_private

        submission_deadline = None
        deadline_raw = body.get("submission_deadline")
        if deadline_raw is not None and str(deadline_raw).strip():
            try:
                submission_deadline = parse_deadline_est(str(deadline_raw))
            except ValueError:
                return _json_error("Invalid submission_deadline", 400)

        join_code = _generate_join_code() if is_private else None

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
                )
                ub = _enroll_user_in_challenge(user, challenge)
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

    challenges = BracketChallenge.objects.filter(
        id__in=challenge_ids
    ).select_related("bracket")
    user_brackets = {
        ub.challenge_id: ub
        for ub in UserBracket.objects.filter(
            user=user, is_master=False, challenge_id__in=challenge_ids
        )
    }

    rows = [
        serializers.challenge_summary(
            c,
            user_bracket_id=ub.id if (ub := user_brackets.get(c.id)) else None,
            user_bracket=user_brackets.get(c.id),
            request=request,
        )
        for c in challenges.order_by("-created_at")
    ]
    return JsonResponse({"challenges": rows})


@require_http_methods(["GET"])
def challenges_public_list(request: HttpRequest) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    qs = (
        BracketChallenge.objects.filter(
            is_public=True,
            instance_type="CHALLENGE",
        )
        .select_related("bracket")
        .order_by("-created_at")
    )
    rows = []
    for c in qs:
        if deadline_passed(c):
            continue
        ub = UserBracket.objects.filter(
            user=user, challenge=c, is_master=False
        ).first()
        rows.append(
            serializers.challenge_summary(
                c,
                user_bracket_id=ub.id if ub else None,
                user_bracket=ub,
                request=request,
            )
        )
    return JsonResponse({"challenges": rows})


@require_http_methods(["GET"])
def challenge_detail(request: HttpRequest, challenge_id: int) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(
        BracketChallenge.objects.select_related("bracket"), pk=challenge_id
    )
    return JsonResponse(
        {"challenge": _challenge_summary_for_user(challenge, user, request)}
    )


@require_http_methods(["GET"])
def challenge_leaderboard(
    request: HttpRequest, challenge_id: int
) -> JsonResponse:
    user = _require_user(request)
    if user is None:
        return _json_error("Authentication required", 401)

    challenge = get_object_or_404(BracketChallenge, pk=challenge_id)
    if not ChallengeParticipant.objects.filter(
        challenge=challenge, user=user
    ).exists():
        ubs = UserBracket.objects.filter(challenge=challenge, is_master=False)
        if not ubs.filter(user=user).exists():
            return _json_error("Forbidden", 403)

    master = challenge.bracket.get_master_bracket()
    stages = list(challenge.bracket.stages.order_by("order"))
    columns = [
        serializers.leaderboard_column(
            key=f"stage:{stage.id}",
            name=stage.name,
        )
        for stage in stages
    ]
    columns.append(
        serializers.leaderboard_column(key="champion", name="Champions")
    )

    entries = []
    for ub in (
        UserBracket.objects.filter(
            challenge=challenge,
            is_master=False,
            submitted_at__isnull=False,
        )
        .select_related("user")
        .order_by("user__username")
    ):
        if master:
            stage_scores: dict[str, int | None] = {
                f"stage:{stage.id}": ub.calculate_stage_score(stage)
                for stage in stages
            }
            stage_scores["champion"] = ub.calculate_champion_score()
            score = ub.calculate_score()
        else:
            stage_scores = {col["key"]: None for col in columns}
            score = None
        entries.append(
            serializers.leaderboard_entry(
                username=ub.user.username,
                user_bracket_id=ub.id,
                score=score,
                stage_scores=stage_scores,
                submitted_at=ub.submitted_at,
            )
        )
    return JsonResponse({"columns": columns, "entries": entries})


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
        challenge = (
            BracketChallenge.objects.select_related("bracket")
            .filter(pk=int(challenge_id_raw), instance_type="CHALLENGE")
            .first()
        )
        if challenge is None:
            return _json_error("Challenge not found", 404)
        if not challenge.is_public:
            return _json_error("This challenge is not public", 403)
    else:
        join_code = _normalize_join_code(body.get("join_code") or "")
        if join_code is None:
            return _json_error(
                "join_code or challenge_id is required", 400
            )
        challenge = (
            BracketChallenge.objects.select_related("bracket")
            .filter(join_code=join_code, instance_type="CHALLENGE")
            .first()
        )
        if challenge is None:
            return _json_error("Invalid join code", 404)

    try:
        ub = _enroll_user_in_challenge(user, challenge)
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
        if not user.is_staff:
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
        first_ko = (
            ub.bracket.stages.filter(stage_type=BracketStage.StageType.KNOCKOUT)
            .order_by("order")
            .first()
        )
        if first_ko and m.stage_id == first_ko.id:
            m.winner = None
            m.save()
            rebuild_knockout_from_first_round(ub)
        else:
            clear_matchup_winner_and_downstream(m)
        m.refresh_from_db()
        return JsonResponse({"matchup": serializers.matchup_public(m)})

    if m.contestant1_id != winner_id and m.contestant2_id != winner_id:
        return _json_error(
            "winner_id must match contestant1 or contestant2 in this matchup", 400
        )

    m.winner = get_object_or_404(BracketContestant, pk=winner_id)
    m.save()
    m.refresh_from_db()
    return JsonResponse({"matchup": serializers.matchup_public(m)})


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
def admin_bracket_templates_list(request: HttpRequest) -> JsonResponse:
    user, err = _staff_user_or_error(request)
    if err is not None:
        return err

    rows = BracketTemplate.objects.order_by("-is_system", "name")
    return JsonResponse(
        {
            "templates": [
                serializers.bracket_template_summary(t) for t in rows
            ]
        }
    )


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
        if BracketChallenge.objects.filter(bracket=bracket).exists():
            return _json_error(
                "Cannot delete a bracket that has challenges. Remove all challenges first.",
                409,
            )
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
    except ValueError as e:
        return _json_error(str(e), 400)

    b = get_object_or_404(
        Bracket.objects.prefetch_related("stages"), pk=bracket.pk
    )
    return JsonResponse(
        {"bracket": serializers.bracket_detail(b, request=request)}
    )
