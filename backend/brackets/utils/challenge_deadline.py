"""Challenge submission deadlines (stored UTC, interpreted/displayed in US Eastern)."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone

from brackets.models import BracketChallenge, UserBracket
from brackets.utils.challenge_types import (
    CHALLENGE,
    POLL,
    TOURNAMENT,
    creates_user_bracket,
    uses_bracket_submission,
)

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
    if challenge.instance_type not in (CHALLENGE, TOURNAMENT, POLL):
        raise ValueError("This activity is not open for joining")
    if challenge.instance_type == CHALLENGE and deadline_passed(challenge):
        raise ValueError("The submission deadline has passed")


def assert_can_edit_picks(ub: UserBracket) -> None:
    if ub.is_master:
        return
    if ub.challenge_id is None:
        return
    challenge = ub.challenge
    if challenge is None:
        return
    if uses_bracket_submission(challenge.instance_type):
        if ub.submitted_at is not None:
            raise ValueError("Bracket already submitted")
        if deadline_passed(challenge):
            raise ValueError("The submission deadline has passed")
        return
    if challenge.instance_type == POLL:
        return
    raise ValueError("Cannot edit picks for this activity")
