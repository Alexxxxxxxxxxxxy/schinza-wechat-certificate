"""Tests for batch import parser (CSV/TXT: 公众号, 文章链接)."""

from __future__ import annotations

from app.batch_import import parse_batch_import

LINK_A = "https://mp.weixin.qq.com/s/AAAA"
LINK_B = "https://mp.weixin.qq.com/s/BBBB"


def test_parse_csv_with_header_skips_header() -> None:
    text = "公众号,文章链接\n数模加油站," + LINK_A + "\n知乎日报," + LINK_B + "\n"
    rows, errors = parse_batch_import(text)
    assert errors == []
    assert [(r.name, r.link) for r in rows] == [("数模加油站", LINK_A), ("知乎日报", LINK_B)]
    assert [r.line for r in rows] == [2, 3]


def test_parse_csv_without_header() -> None:
    text = "数模加油站," + LINK_A + "\n知乎日报," + LINK_B + "\n"
    rows, errors = parse_batch_import(text)
    assert errors == []
    assert [(r.name, r.link) for r in rows] == [("数模加油站", LINK_A), ("知乎日报", LINK_B)]


def test_parse_txt_tab_separated_without_header() -> None:
    text = "数模加油站\t" + LINK_A + "\n知乎日报\t" + LINK_B + "\n"
    rows, errors = parse_batch_import(text)
    assert errors == []
    assert [(r.name, r.link) for r in rows] == [("数模加油站", LINK_A), ("知乎日报", LINK_B)]


def test_parse_skips_blank_lines() -> None:
    text = "数模加油站," + LINK_A + "\n\n   \n知乎日报," + LINK_B + "\n"
    rows, errors = parse_batch_import(text)
    assert errors == []
    assert len(rows) == 2


def test_parse_reports_short_rows_and_keeps_valid_rows() -> None:
    text = "数模加油站," + LINK_A + "\n只有名称没有链接\n知乎日报," + LINK_B + "\n"
    rows, errors = parse_batch_import(text)
    assert [(r.name, r.link) for r in rows] == [("数模加油站", LINK_A), ("知乎日报", LINK_B)]
    assert len(errors) == 1
    assert "第 2 行" in errors[0]


def test_parse_rejects_non_wechat_link() -> None:
    text = "数模加油站,https://example.com/not-wechat\n"
    rows, errors = parse_batch_import(text)
    assert rows == []
    assert len(errors) == 1
    assert "第 1 行" in errors[0]


def test_parse_rejects_empty_name() -> None:
    text = "," + LINK_A + "\n"
    rows, errors = parse_batch_import(text)
    assert rows == []
    assert len(errors) == 1
    assert "第 1 行" in errors[0]


def test_parse_header_variants() -> None:
    for header in (
        "公众号,文章链接",
        "公众号名称,链接",
        "账号,url",
        "名称,文章链接",
        "name,link",
        "account,article_url",
        "昵称,文章url",
    ):
        text = header + "\n数模加油站," + LINK_A + "\n"
        rows, errors = parse_batch_import(text)
        assert errors == [], header
        assert [(r.name, r.link) for r in rows] == [("数模加油站", LINK_A)], header


def test_parse_uses_first_two_columns() -> None:
    text = "数模加油站," + LINK_A + ",多余列,再多余\n"
    rows, errors = parse_batch_import(text)
    assert errors == []
    assert [(r.name, r.link) for r in rows] == [("数模加油站", LINK_A)]


def test_parse_empty_text_returns_no_rows() -> None:
    rows, errors = parse_batch_import("")
    assert rows == []
    assert errors == []


def test_parse_tolerates_bom() -> None:
    text = "\ufeff公众号,文章链接\n数模加油站," + LINK_A + "\n"
    rows, errors = parse_batch_import(text)
    assert errors == []
    assert [(r.name, r.link) for r in rows] == [("数模加油站", LINK_A)]
