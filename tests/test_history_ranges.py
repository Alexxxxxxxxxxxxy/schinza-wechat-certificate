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
