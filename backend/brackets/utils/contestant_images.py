"""Resolve display image URLs for contestants (flags, club badges, uploads)."""

from __future__ import annotations

import json
from urllib.request import urlopen

from django.core.cache import cache

from brackets.models import Contestant

FLAGCDN_BASE = "https://flagcdn.com"
NATION_TAG_NAME = "nation"
CLUB_TAG_NAME = "club"
THESPORTSDB_LOOKUP_URL = "https://www.thesportsdb.com/api/v1/json/3/lookupteam.php?id={team_id}"

# TheSportsDB team id -> badge CDN URL. Used when the free API key cannot look up
# arbitrary teams (it returns Arsenal for every request).
CLUB_BADGE_URLS: dict[str, str] = {
    "133600": "https://r2.thesportsdb.com/images/media/team/badge/xwwvyt1448811086.png",
    "133601": "https://r2.thesportsdb.com/images/media/team/badge/jykrpv1717309891.png",
    "133602": "https://r2.thesportsdb.com/images/media/team/badge/kfaher1737969724.png",
    "133603": "https://r2.thesportsdb.com/images/media/team/badge/tprtus1448813498.png",
    "133604": "https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png",
    "133610": "https://r2.thesportsdb.com/images/media/team/badge/yvwvtu1448813215.png",
    "133612": "https://r2.thesportsdb.com/images/media/team/badge/xzqdr11517660252.png",
    "133613": "https://r2.thesportsdb.com/images/media/team/badge/vwpvry1467462651.png",
    "133615": "https://r2.thesportsdb.com/images/media/team/badge/eqayrf1523184794.png",
    "133616": "https://r2.thesportsdb.com/images/media/team/badge/dfyfhl1604094109.png",
    "133619": "https://r2.thesportsdb.com/images/media/team/badge/ywypts1448810904.png",
    "133623": "https://r2.thesportsdb.com/images/media/team/badge/ql7nl31686893820.png",
    "133632": "https://r2.thesportsdb.com/images/media/team/badge/ia6i3m1656014992.png",
    "133635": "https://r2.thesportsdb.com/images/media/team/badge/jcgrml1756649030.png",
    "133636": "https://r2.thesportsdb.com/images/media/team/badge/yutyxs1467459956.png",
    "133650": "https://r2.thesportsdb.com/images/media/team/badge/tqo8ge1716960353.png",
    "133664": "https://r2.thesportsdb.com/images/media/team/badge/01ogkh1716960412.png",
    "133714": "https://r2.thesportsdb.com/images/media/team/badge/rwqrrq1473504808.png",
    "133720": "https://r2.thesportsdb.com/images/media/team/badge/bk4qjs1546440351.png",
    "133729": "https://r2.thesportsdb.com/images/media/team/badge/0ulh3q1719984315.png",
    "133738": "https://r2.thesportsdb.com/images/media/team/badge/vwvwrw1473502969.png",
    "133739": "https://r2.thesportsdb.com/images/media/team/badge/wq9sir1639406443.png",
    "133599": "https://r2.thesportsdb.com/images/media/team/badge/u9qr031621593327.png",
    "134301": "https://r2.thesportsdb.com/images/media/team/badge/y08nak1534071116.png",
    "134355": "https://r2.thesportsdb.com/images/media/team/badge/grv1aw1546453779.png",
    "134777": "https://r2.thesportsdb.com/images/media/team/badge/lhwuiz1621593302.png",
}

# Contestant.identifier -> FlagCDN code
# Includes UK constituent nations (gb-eng/gb-sct/gb-wls/gb-nir).
NATION_FLAG_CODES: dict[str, str] = {
    "algeria": "dz",
    "argentina": "ar",
    "australia": "au",
    "austria": "at",
    "belgium": "be",
    "bosnia-herzegovina": "ba",
    "brazil": "br",
    "cabo-verde": "cv",
    "canada": "ca",
    "colombia": "co",
    "congo-dr": "cd",
    "croatia": "hr",
    "curacao": "cw",
    "czechia": "cz",
    "cote-divoire": "ci",
    "ecuador": "ec",
    "egypt": "eg",
    "england": "gb-eng",
    "france": "fr",
    "germany": "de",
    "ghana": "gh",
    "haiti": "ht",
    "iran": "ir",
    "iraq": "iq",
    "japan": "jp",
    "jordan": "jo",
    "mexico": "mx",
    "morocco": "ma",
    "netherlands": "nl",
    "new-zealand": "nz",
    "norway": "no",
    "panama": "pa",
    "paraguay": "py",
    "portugal": "pt",
    "qatar": "qa",
    "saudi-arabia": "sa",
    "scotland": "gb-sct",
    "senegal": "sn",
    "south-africa": "za",
    "south-korea": "kr",
    "spain": "es",
    "sweden": "se",
    "switzerland": "ch",
    "tunisia": "tn",
    "turkiye": "tr",
    "united-states": "us",
    "uruguay": "uy",
    "uzbekistan": "uz",
    "wales": "gb-wls",
    "northern-ireland": "gb-nir",
}


def nation_flag_url(contestant: Contestant | None) -> str | None:
    if contestant is None:
        return None
    if not contestant.tags.filter(name__iexact=NATION_TAG_NAME).exists():
        return None
    code = NATION_FLAG_CODES.get((contestant.identifier or "").strip().lower())
    if not code:
        return None
    return f"{FLAGCDN_BASE}/{code}.svg"


def _club_team_id(contestant: Contestant) -> str | None:
    meta = contestant.metadata if isinstance(contestant.metadata, dict) else {}
    for key in (
        "the_sports_db_team_id",
        "thesportsdb_team_id",
        "sportsdb_team_id",
        "idTeam",
    ):
        raw = meta.get(key)
        if raw is None:
            continue
        team_id = str(raw).strip()
        if team_id:
            return team_id
    return None


def club_logo_url(contestant: Contestant | None) -> str | None:
    """Resolve a club crest URL from TheSportsDB for club-tagged contestants."""
    if contestant is None:
        return None
    if not contestant.tags.filter(name__iexact=CLUB_TAG_NAME).exists():
        return None
    team_id = _club_team_id(contestant)
    if not team_id:
        return None

    team_id = str(team_id)
    static_logo = CLUB_BADGE_URLS.get(team_id)
    if static_logo:
        return static_logo

    cache_key = f"thesportsdb:team:{team_id}:badge"
    cached = cache.get(cache_key)
    if cached is not None:
        logo = str(cached).strip()
        if logo:
            return logo
        return static_logo

    url = THESPORTSDB_LOOKUP_URL.format(team_id=team_id)
    try:
        with urlopen(url, timeout=2.5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        cache.set(cache_key, "", 6 * 60 * 60)
        return static_logo

    teams = payload.get("teams") if isinstance(payload, dict) else None
    team = teams[0] if isinstance(teams, list) and teams else None
    if not isinstance(team, dict):
        cache.set(cache_key, "", 6 * 60 * 60)
        return static_logo
    # Free-tier TheSportsDB can return Arsenal for arbitrary requests.
    # Prevent showing an incorrect crest when returned team does not match
    # the requested team ID.
    returned_team_id = str(team.get("idTeam") or "").strip()
    if returned_team_id and returned_team_id != team_id:
        cache.set(cache_key, "", 6 * 60 * 60)
        return static_logo
    logo = (team.get("strBadge") or team.get("strLogo") or "").strip()
    cache.set(cache_key, logo, 6 * 60 * 60)
    return logo or static_logo


def resolve_contestant_image_url(contestant: Contestant | None) -> str | None:
    """Display image with API sources first, then uploaded/custom fallback."""
    if contestant is None:
        return None
    flag = nation_flag_url(contestant)
    if flag:
        return flag
    club_logo = club_logo_url(contestant)
    if club_logo:
        return club_logo
    if getattr(contestant, "photo", None) and contestant.photo:
        return contestant.photo.url
    if contestant.image_url:
        return contestant.image_url
    return None
