"""Stable history-account selection helpers (labels include a changing countdown)."""

from __future__ import annotations

import re

_COUNTDOWN_RE = re.compile(r"^(.*)（剩余 ")


def _name_prefix(label: str) -> str:
    m = _COUNTDOWN_RE.match(label or "")
    if m:
        return m.group(1)
    return (label or "").strip()


def resolve_account_id(
    options: list[tuple[str, str]],
    *,
    current_label: str,
    preferred_id: str | None,
) -> str | None:
    """Map UI selection to account id; tolerate countdown text changes."""
    if not options:
        return None
    ids = {aid for _lb, aid in options}
    if preferred_id and preferred_id in ids:
        return preferred_id
    for lb, aid in options:
        if lb == current_label:
            return aid
    prefix = _name_prefix(current_label)
    if prefix:
        matches = [aid for lb, aid in options if _name_prefix(lb) == prefix]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            # Prefer exact name match among duplicates if possible
            return matches[0]
    return None


def pick_label_for_account_id(
    options: list[tuple[str, str]],
    account_id: str | None,
) -> str | None:
    if not options:
        return None
    if account_id:
        for lb, aid in options:
            if aid == account_id:
                return lb
    return options[0][0]
