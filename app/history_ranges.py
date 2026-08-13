"""History fetch window presets for the desktop UI."""

from __future__ import annotations

# (label, days); days=None 表示「全部」——不做日期过滤，一直翻页到没有更多。
HISTORY_RANGES: list[tuple[str, int | None]] = [
    ("近 7 天", 7),
    ("近 30 天", 30),
    ("近 90 天", 90),
    ("全部", None),
]

ALL_LABEL = "全部"
CUSTOM_LABEL = "自定义天数"
RANGE_LABEL = "日期范围"

# 预设标签 + 交互式「自定义天数 / 日期范围」入口（实际值由 UI 弹窗输入）。
HISTORY_RANGE_LABELS = [label for label, _days in HISTORY_RANGES] + [CUSTOM_LABEL, RANGE_LABEL]

DEFAULT_HISTORY_DAYS = 7
CUSTOM_DAYS_DEFAULT = 30
MAX_CUSTOM_DAYS = 3650  # 10 年


def days_for_label(label: str) -> int | None:
    """返回预设标签对应的天数；None 表示「全部」（不过滤日期）。

    「自定义天数」没有固定值，由 UI 弹窗输入，因此这里兜底返回默认天数。
    """
    if label == CUSTOM_LABEL:
        return DEFAULT_HISTORY_DAYS
    for lb, days in HISTORY_RANGES:
        if lb == label:
            return days
    return DEFAULT_HISTORY_DAYS


def label_for_days(days: int | None) -> str:
    """把天数映射回预设标签；None → 全部，非预设值 → 自定义天数。"""
    if days is None:
        return ALL_LABEL
    for lb, d in HISTORY_RANGES:
        if d is not None and d == int(days):
            return lb
    return CUSTOM_LABEL


def range_text(days: int | None) -> str:
    """用户可见的范围文案：'近 7 天' 或 '全部历史'。"""
    return "全部历史" if days is None else f"近 {days} 天"


def date_range_text(start_iso: str, end_iso: str) -> str:
    """日期区间文案：'2025-06-30 至 2025-07-30'。"""
    return f"{start_iso} 至 {end_iso}"
