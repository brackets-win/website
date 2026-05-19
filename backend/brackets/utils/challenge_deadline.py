"""Challenge submission deadlines (stored UTC, interpreted/displayed in US Eastern)."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone

from brackets.models import BracketChallenge, UserBracket

EASTERN = ZoneInfo("America/New_York")


def parse_deadline_est(raw: str) -> datetime:
    """
    Parse a deadline from the client.

    Accepts:
    - ``YYYY-MM-DDTHH:MM`` (datetime-local) as US Eastern wall time
    - ISO-8601 with offset or ``Z`` (converted to aware UTC)
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("submission_deadline is required")

    if "T" in s and len(s) <= 16 and s[10] == "T":
        naive = datetime.fromisoformat(s)
        return naive.replace(tzinfo=EASTERN)

    parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=EASTERN)
    return parsed.astimezone(dt_timezone.utc)


def deadline_passed(challenge: BracketChallenge, *, now: datetime | None = None) -> bool:
    if challenge.submission_deadline is None:
        return False
    ref = now or timezone.now()
    deadline = challenge.submission_deadline
    if timezone.is_naive(deadline):
        deadline = timezone.make_aware(deadline)
    return ref >= deadline


def assert_can_join(challenge: BracketChallenge) -> None:
    if challenge.instance_type != "CHALLENGE":
        raise ValueError("This challenge is not open for joining")
    if deadline_passed(challenge):
        raise ValueError("The submission deadline has passed")


def assert_can_edit_picks(ub: UserBracket) -> None:
    if ub.is_master:
        return
    if ub.submitted_at is not None:
        raise ValueError("Bracket already submitted")
    if ub.challenge_id is None:
        return
    challenge = ub.challenge
    if challenge and deadline_passed(challenge):
        raise ValueError("The submission deadline has passed")
