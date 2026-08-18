from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.history_ranges import (  # noqa: E402
    HISTORY_RANGE_LABELS,
    days_for_label,
    label_for_days,
)


def test_history_range_presets():
    assert "近 7 天" in HISTORY_RANGE_LABELS
    assert "近 30 天" in HISTORY_RANGE_LABELS
    assert "近 90 天" in HISTORY_RANGE_LABELS
    assert days_for_label("近 7 天") == 7
    assert days_for_label("近 30 天") == 30
    assert days_for_label("近 90 天") == 90
    assert label_for_days(30) == "近 30 天"
    assert days_for_label("未知") == 7


def test_all_and_custom_labels():
    """「全部」与「自定义天数」作为新的范围选项存在。"""
    assert "全部" in HISTORY_RANGE_LABELS
    assert "自定义天数" in HISTORY_RANGE_LABELS
    assert days_for_label("全部") is None
    assert label_for_days(None) == "全部"
    assert label_for_days(15) == "自定义天数"


def test_date_range_label_included() -> None:
    from app.history_ranges import HISTORY_RANGE_LABELS, RANGE_LABEL
    assert RANGE_LABEL == "日期范围"
    assert RANGE_LABEL in HISTORY_RANGE_LABELS


def test_date_range_text() -> None:
    from app.history_ranges import date_range_text
    assert date_range_text("2025-06-30", "2025-07-30") == "2025-06-30 至 2025-07-30"
