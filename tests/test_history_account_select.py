from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.history_account_select import (  # noqa: E402
    pick_label_for_account_id,
    resolve_account_id,
)


def test_resolve_keeps_id_when_countdown_label_changes():
    options = [
        ("甲号（剩余 10:00）", "id-a"),
        ("乙号（剩余 09:59）", "id-b"),
    ]
    # User had selected 乙号, but old label text is stale
    aid = resolve_account_id(
        options,
        current_label="乙号（剩余 10:01）",
        preferred_id="id-b",
    )
    assert aid == "id-b"
    label = pick_label_for_account_id(options, "id-b")
    assert label == "乙号（剩余 09:59）"


def test_resolve_falls_back_to_name_prefix_without_preferred():
    options = [
        ("甲号（剩余 10:00）", "id-a"),
        ("乙号（剩余 09:59）", "id-b"),
    ]
    aid = resolve_account_id(
        options,
        current_label="乙号（剩余 10:01）",
        preferred_id=None,
    )
    assert aid == "id-b"


def test_pick_defaults_to_first_only_when_unknown():
    options = [
        ("甲号（剩余 10:00）", "id-a"),
        ("乙号（剩余 09:59）", "id-b"),
    ]
    assert pick_label_for_account_id(options, "missing") == "甲号（剩余 10:00）"
    assert pick_label_for_account_id([], "id-a") is None
