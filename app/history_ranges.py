"""History fetch window presets for the desktop UI."""

from __future__ import annotations

HISTORY_RANGES: list[tuple[str, int]] = [
    ("近 7 天", 7),
    ("近 30 天", 30),
    ("近 90 天", 90),
]

HISTORY_RANGE_LABELS = [label for label, _days in HISTORY_RANGES]
DEFAULT_HISTORY_DAYS = 7


def days_for_label(label: str) -> int:
    for lb, days in HISTORY_RANGES:
        if lb == label:
            return days
    return DEFAULT_HISTORY_DAYS


def label_for_days(days: int) -> str:
    for lb, d in HISTORY_RANGES:
        if d == int(days):
            return lb
    return label_for_days(DEFAULT_HISTORY_DAYS)
