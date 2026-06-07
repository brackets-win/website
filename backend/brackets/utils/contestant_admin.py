"""Admin helpers for contestant catalog fields."""

from __future__ import annotations

import json
from typing import Any

from brackets.models import Contestant, ContestantTag
from brackets.utils.bracket_structure_config import parse_bracket_metadata


def parse_tag_names(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(n).strip() for n in raw if str(n).strip()]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(n).strip() for n in parsed if str(n).strip()]
        except json.JSONDecodeError:
            pass
    return [p.strip() for p in text.split(",") if p.strip()]


def parse_tag_ids(raw: Any) -> list[int]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [int(x) for x in raw]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [int(x) for x in parsed]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return [int(p.strip()) for p in text.split(",") if p.strip()]


def set_contestant_tags(
    contestant: Contestant,
    *,
    tag_ids: list[int] | None = None,
    tag_names: list[str] | None = None,
) -> None:
    ids: list[int] = list(tag_ids or [])
    for name in tag_names or []:
        label = name.strip()[:50]
        if not label:
            continue
        tag, _ = ContestantTag.objects.get_or_create(name=label)
        if tag.id not in ids:
            ids.append(tag.id)
    contestant.tags.set(ids)


def apply_contestant_admin_fields(
    contestant: Contestant, body: dict[str, Any]
) -> list[str]:
    """Mutate contestant from admin body; return ``update_fields``."""
    fields: list[str] = []

    if "image_url" in body:
        contestant.image_url = str(body.get("image_url") or "").strip()
        fields.append("image_url")

    if "metadata" in body:
        contestant.metadata = parse_bracket_metadata(body["metadata"])
        fields.append("metadata")

    if "tag_ids" in body or "tag_names" in body:
        tag_ids = (
            parse_tag_ids(body["tag_ids"]) if "tag_ids" in body else []
        )
        tag_names = (
            parse_tag_names(body["tag_names"]) if "tag_names" in body else []
        )
        set_contestant_tags(contestant, tag_ids=tag_ids, tag_names=tag_names)

    return fields
