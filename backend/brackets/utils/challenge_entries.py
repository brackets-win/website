"""Per-user entry limits on bracket challenges."""

from __future__ import annotations

from django.db.models import Count, Max

from brackets.models import BracketChallenge, UserBracket
from brackets.utils.challenge_types import CHALLENGE


def user_entry_count(user, challenge: BracketChallenge) -> int:
    return UserBracket.objects.filter(
        user=user, challenge=challenge, is_master=False
    ).count()


def user_entries_for_challenge(user, challenge: BracketChallenge):
    return UserBracket.objects.filter(
        user=user, challenge=challenge, is_master=False
    ).order_by("-created_at")


def user_has_submitted_challenge(user, challenge: BracketChallenge) -> bool:
    """True when the user has at least one submitted entry in this challenge."""
    if challenge.instance_type != CHALLENGE:
        return True
    return UserBracket.objects.filter(
        user=user,
        challenge=challenge,
        is_master=False,
        submitted_at__isnull=False,
    ).exists()


def can_add_challenge_entry(user, challenge: BracketChallenge) -> bool:
    return user_entry_count(user, challenge) < challenge.max_entries


def assert_can_add_entry(user, challenge: BracketChallenge) -> None:
    if not can_add_challenge_entry(user, challenge):
        raise ValueError(
            f"This challenge allows at most {challenge.max_entries} "
            f"{'entry' if challenge.max_entries == 1 else 'entries'} per person."
        )


def assert_display_name_available(
    challenge: BracketChallenge,
    user,
    display_name: str,
    *,
    exclude_user_bracket_id: int | None = None,
) -> None:
    qs = UserBracket.objects.filter(
        challenge=challenge,
        user=user,
        is_master=False,
        display_name__iexact=display_name.strip(),
    )
    if exclude_user_bracket_id is not None:
        qs = qs.exclude(pk=exclude_user_bracket_id)
    if qs.exists():
        raise ValueError("You already have an entry with this name.")


def max_entries_in_use(challenge: BracketChallenge) -> int:
    """Highest entry count any one participant currently has."""
    agg = (
        UserBracket.objects.filter(challenge=challenge, is_master=False)
        .values("user_id")
        .annotate(n=Count("id"))
        .aggregate(m=Max("n"))
    )
    return int(agg["m"] or 0)


def normalize_max_entries(raw, *, instance_type: str) -> int:
    if instance_type != CHALLENGE:
        return 1
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError("max_entries must be a positive integer") from None
    if value < 1:
        raise ValueError("max_entries must be at least 1")
    if value > 50:
        raise ValueError("max_entries cannot exceed 50")
    return value
