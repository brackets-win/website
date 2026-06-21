"""Prefix streak question text with nation flag emojis in canonical matchup order."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from brackets.models import Contestant
from brackets.utils.contestant_images import NATION_FLAG_CODES, NATION_TAG_NAME

# Common spellings in question copy -> Contestant.name
NAME_ALIASES: dict[str, str] = {
    "bosnia & herzegovina": "Bosnia and Herzegovina",
    "cote d'ivoire": "Ivory Coast",
    "côte d'ivoire": "Ivory Coast",
    "curacao": "Curaçao",
    "cape verde": "Cabo Verde",
    "turkey": "Türkiye",
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "dr congo": "Congo DR",
    "democratic republic of the congo": "Congo DR",
    "korea republic": "South Korea",
    "republic of korea": "South Korea",
}

SUBDIVISION_FLAG_EMOJI: dict[str, str] = {
    "gb-eng": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
    "gb-sct": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",
    "gb-wls": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",
    "gb-nir": "\U0001F3F4\U000E0067\U000E0062\U000E006E\U000E0069\U000E0072\U000E007F",
}

_ONE_FLAG = r"(?:[\U0001F1E6-\U0001F1FF]{2}|\U0001F3F4[\U000E0020-\U000E007E]+)"
_FLAG_PREFIX_RE = re.compile(rf"^(?:{_ONE_FLAG}){{2}}\s+")


@dataclass(frozen=True)
class NationMatch:
    canonical_name: str
    identifier: str
    search_terms: tuple[str, ...]


@dataclass
class PrefixPlan:
    question_id: int
    old_text: str
    new_text: str
    team_a: str
    team_b: str


@dataclass
class PrefixReport:
    updated: list[PrefixPlan]
    skipped_already_prefixed: list[int]
    skipped_non_match: list[tuple[int, str]]
    skipped_no_order: list[tuple[int, str, tuple[str, str]]]
    conflicts: list[tuple[tuple[str, str], tuple[str, str], tuple[str, str]]]


def _normalize_for_match(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _iso_flag_emoji(code: str) -> str:
    lowered = code.strip().lower()
    if lowered in SUBDIVISION_FLAG_EMOJI:
        return SUBDIVISION_FLAG_EMOJI[lowered]
    alpha = lowered.split("-", 1)[0]
    if len(alpha) != 2 or not alpha.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("a")) for ch in alpha)


def nation_flag_emoji(identifier: str) -> str:
    code = NATION_FLAG_CODES.get((identifier or "").strip().lower())
    if not code:
        return ""
    return _iso_flag_emoji(code)


def load_nation_matches() -> list[NationMatch]:
    contestants = (
        Contestant.objects.filter(tags__name__iexact=NATION_TAG_NAME)
        .distinct()
        .order_by("name")
    )
    matches: list[NationMatch] = []
    for contestant in contestants:
        terms = {contestant.name.strip()}
        alias_key = _normalize_for_match(contestant.name)
        if alias_key in NAME_ALIASES:
            terms.add(NAME_ALIASES[alias_key])
        for alias, canonical in NAME_ALIASES.items():
            if canonical == contestant.name:
                terms.add(alias)
        matches.append(
            NationMatch(
                canonical_name=contestant.name,
                identifier=contestant.identifier,
                search_terms=tuple(sorted(terms, key=len, reverse=True)),
            )
        )
    return matches


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    escaped = escaped.replace(r"\&", r"(?:&|and)")
    return re.compile(rf"(?<![\w]){escaped}(?![\w])", re.IGNORECASE)


def _teams_in_text(text: str, nations: list[NationMatch]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for nation in nations:
        for term in nation.search_terms:
            if _term_pattern(term).search(text):
                if nation.canonical_name not in seen:
                    found.append(nation.canonical_name)
                    seen.add(nation.canonical_name)
                break
    return found


def _vs_pair(text: str, nations: list[NationMatch]) -> tuple[str, str] | None:
    for left in nations:
        for right in nations:
            if left.canonical_name == right.canonical_name:
                continue
            for left_term in left.search_terms:
                for right_term in right.search_terms:
                    pattern = re.compile(
                        rf"(?<![\w]){re.escape(left_term)}\s+vs\.?\s+{re.escape(right_term)}(?![\w])",
                        re.IGNORECASE,
                    )
                    if pattern.search(text):
                        return left.canonical_name, right.canonical_name
    return None


def build_matchup_order(
    question_texts: list[str],
    nations: list[NationMatch],
) -> tuple[dict[frozenset[str], tuple[str, str]], list[tuple[tuple[str, str], tuple[str, str], str]]]:
    order: dict[frozenset[str], tuple[str, str]] = {}
    conflicts: list[tuple[tuple[str, str], tuple[str, str], str]] = []

    for text in question_texts:
        pair = _vs_pair(text, nations)
        if pair is None:
            continue
        key = frozenset(pair)
        if key not in order:
            order[key] = pair
            continue
        if order[key] != pair:
            conflicts.append((order[key], pair, text))

    return order, conflicts


def _strip_existing_prefix(text: str) -> str:
    stripped = text
    while True:
        next_text = _FLAG_PREFIX_RE.sub("", stripped, count=1)
        if next_text == stripped:
            return stripped
        stripped = next_text


def plan_question_prefixes(
    questions: list[tuple[int, str]],
    nations: list[NationMatch] | None = None,
) -> PrefixReport:
    nations = nations if nations is not None else load_nation_matches()
    name_to_identifier = {n.canonical_name: n.identifier for n in nations}

    texts = [_strip_existing_prefix(text) for _, text in questions]
    matchup_order, order_conflicts = build_matchup_order(texts, nations)

    updated: list[PrefixPlan] = []
    skipped_already_prefixed: list[int] = []
    skipped_non_match: list[tuple[int, str]] = []
    skipped_no_order: list[tuple[int, str, tuple[str, str]]] = []

    for (question_id, original_text), body in zip(questions, texts, strict=True):
        if _FLAG_PREFIX_RE.match(original_text):
            skipped_already_prefixed.append(question_id)

        teams = _teams_in_text(body, nations)
        if len(teams) != 2:
            skipped_non_match.append((question_id, body))
            continue

        key = frozenset(teams)
        ordered = matchup_order.get(key)
        if ordered is None:
            skipped_no_order.append((question_id, body, tuple(sorted(teams))))
            continue

        flag_a = nation_flag_emoji(name_to_identifier[ordered[0]])
        flag_b = nation_flag_emoji(name_to_identifier[ordered[1]])
        if not flag_a or not flag_b:
            skipped_no_order.append((question_id, body, ordered))
            continue

        prefix = f"{flag_a}{flag_b} "
        new_text = prefix + body
        if new_text == original_text:
            continue

        updated.append(
            PrefixPlan(
                question_id=question_id,
                old_text=original_text,
                new_text=new_text,
                team_a=ordered[0],
                team_b=ordered[1],
            )
        )

    conflicts = [
        (existing, incoming, snippet)
        for existing, incoming, snippet in order_conflicts
    ]

    return PrefixReport(
        updated=updated,
        skipped_already_prefixed=skipped_already_prefixed,
        skipped_non_match=skipped_non_match,
        skipped_no_order=skipped_no_order,
        conflicts=conflicts,
    )
