from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.capture_target import expected_biz, resolve_capture_target  # noqa: E402


def _acc(aid, name, biz="", url="", cred_biz=""):
    row = {"id": aid, "name": name, "biz": biz, "article_url": url, "credentials": {}}
    if cred_biz:
        row["credentials"] = {"__biz": cred_biz}
    return row


def test_expected_biz_prefers_row_biz_then_cred_then_url():
    assert expected_biz(_acc("1", "A", biz="MzA==")) == "MzA=="
    assert expected_biz(_acc("1", "A", cred_biz="MzB==")) == "MzB=="
    assert (
        expected_biz(
            _acc(
                "1",
                "A",
                url="https://mp.weixin.qq.com/s?__biz=MzC%3D%3D&mid=1",
            )
        )
        == "MzC=="
    )


def test_resolve_pending_hit():
    accounts = [
        _acc("a", "甲", biz="biz-a"),
        _acc("b", "乙", biz="biz-b"),
    ]
    r = resolve_capture_target(accounts=accounts, pending_id="a", cred_biz="biz-a")
    assert r.kind == "pending"
    assert r.account_id == "a"


def test_resolve_other_account_when_pending_differs():
    accounts = [
        _acc("a", "甲", biz="biz-a"),
        _acc("b", "乙", biz="biz-b"),
    ]
    r = resolve_capture_target(accounts=accounts, pending_id="a", cred_biz="biz-b")
    assert r.kind == "other_account"
    assert r.account_id == "b"
    assert r.target_name == "乙"
    assert r.pending_name == "甲"


def test_resolve_unknown():
    accounts = [_acc("a", "甲", biz="biz-a")]
    r = resolve_capture_target(accounts=accounts, pending_id="a", cred_biz="biz-x")
    assert r.kind == "unknown"
    assert r.account_id is None


def test_resolve_empty_biz_unknown():
    accounts = [_acc("a", "甲", biz="biz-a")]
    r = resolve_capture_target(accounts=accounts, pending_id="a", cred_biz="")
    assert r.kind == "unknown"


def test_pending_without_expected_biz_keeps_pending_if_unclaimed():
    """Legacy: pending has no biz; cred_biz not owned by anyone → apply to pending."""
    accounts = [_acc("a", "甲"), _acc("b", "乙", biz="biz-b")]
    r = resolve_capture_target(accounts=accounts, pending_id="a", cred_biz="biz-new")
    assert r.kind == "pending"
    assert r.account_id == "a"


def test_pending_without_expected_biz_does_not_steal_owned_biz():
    accounts = [_acc("a", "甲"), _acc("b", "乙", biz="biz-b")]
    r = resolve_capture_target(accounts=accounts, pending_id="a", cred_biz="biz-b")
    assert r.kind == "other_account"
    assert r.account_id == "b"
