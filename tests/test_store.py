"""AccountStore tests."""

from __future__ import annotations

from pathlib import Path

from app.store import AccountStore


def _store(tmp_path: Path) -> AccountStore:
    return AccountStore(tmp_path / "accounts.json")


def test_add_pending_awaiting() -> None:
    pass


def test_set_biz_sets_row_and_credentials(tmp_path: Path) -> None:
    st = _store(tmp_path)
    a = st.add_pending(name="A", article_url="https://mp.weixin.qq.com/s/short")
    st.set_biz(a["id"], "BIZ_X")
    row = st.get(a["id"])
    assert row["biz"] == "BIZ_X"
    assert row["credentials"]["__biz"] == "BIZ_X"
