"""Credential list name-filter helper tests."""

from __future__ import annotations

from app.ui import _matches_name_filter


def test_empty_query_matches_all() -> None:
    assert _matches_name_filter("平安中大", "")
    assert _matches_name_filter("平安中大", "   ")
    assert _matches_name_filter("", "")


def test_case_insensitive_substring() -> None:
    assert _matches_name_filter("数模加油站", "模")
    assert _matches_name_filter("数模加油站", "加油站")
    assert _matches_name_filter("Zhihu Daily", "zhihu")


def test_no_match() -> None:
    assert not _matches_name_filter("数模加油站", "知乎")
    assert not _matches_name_filter("", "知乎")


def test_query_matches_whitespace_trimmed() -> None:
    assert _matches_name_filter("平安中大", " 平安 ")


def test_iso_date_to_ts() -> None:
    from app.ui import _iso_date_to_ts

    s = _iso_date_to_ts("2025-06-30")
    e = _iso_date_to_ts("2025-06-30", end_of_day=True)
    assert e - s == 86399
    assert _iso_date_to_ts("2025-07-30") > s
