"""Tournament / bracket results-entry modes (group + knockout)."""

from __future__ import annotations

from typing import Any

GROUP_STANDINGS = "standings"
GROUP_TABLE = "table"
GROUP_FIXTURES = "fixtures"
GROUP_MODES = frozenset({GROUP_STANDINGS, GROUP_TABLE, GROUP_FIXTURES})

KO_WINNER = "winner"
KO_SCORE = "score"
KO_MODES = frozenset({KO_WINNER, KO_SCORE})


def normalize_results_entry(raw: Any) -> dict[str, str]:
    """
    Return ``{"group": ..., "knockout": ...}`` with defaults.

    Unknown keys/values fall back to standings / winner.
    """
    data = raw if isinstance(raw, dict) else {}
    group = str(data.get("group") or GROUP_STANDINGS).strip().lower()
    knockout = str(data.get("knockout") or KO_WINNER).strip().lower()
    if group not in GROUP_MODES:
        group = GROUP_STANDINGS
    if knockout not in KO_MODES:
        knockout = KO_WINNER
    return {"group": group, "knockout": knockout}


def results_entry_from_bracket(bracket) -> dict[str, str]:
    meta = bracket.metadata if isinstance(bracket.metadata, dict) else {}
    return normalize_results_entry(meta.get("results_entry"))


def merge_results_entry_into_metadata(
    metadata: dict[str, Any] | None,
    results_entry: Any,
) -> dict[str, Any]:
    meta = dict(metadata or {})
    meta["results_entry"] = normalize_results_entry(results_entry)
    return meta
