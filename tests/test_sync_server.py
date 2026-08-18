from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.sync_server import (  # noqa: E402
    build_account_payload,
    chunk_accounts,
    parse_school_accounts_csv,
    upload_credentials_batch,
)


def test_parse_school_accounts_csv_strips_bom():
    text = "\ufeffschool_id,school_name,nickname,source\n2,中山大学,鸭大情报局,学校\n,中山大学,优质号,优质\n"
    rows = parse_school_accounts_csv(text)
    assert rows[0] == {"school_id": "2", "school_name": "中山大学", "nickname": "鸭大情报局", "source": "学校"}
    assert rows[1]["school_id"] == ""
    assert rows[1]["source"] == "优质"


def test_parse_school_accounts_csv_skips_empty_rows_and_normalizes_source():
    text = "school_id,school_name,nickname,source\n1,复旦,复旦新闻,, \n\n2,浙大,浙大头条,未知\n"
    rows = parse_school_accounts_csv(text)
    assert rows[0]["source"] == "学校"  # 空 source 归为学校
    assert rows[1]["source"] == "学校"  # 未知 source 归为学校


def _account(name, biz="MzA==", uin="1", key="k"):
    return {
        "id": "id-1",
        "name": name,
        "status": "active",
        "credentials": {"__biz": biz, "uin": uin, "key": key, "pass_ticket": "pt"},
    }


def test_build_account_payload_matches_by_name():
    rows = [
        {"school_id": "2", "school_name": "中山大学", "nickname": "鸭大情报局", "source": "学校"},
        {"school_id": "", "school_name": "", "nickname": "优质大号", "source": "优质"},
    ]
    p = build_account_payload(_account("鸭大情报局"), rows)
    assert p is not None
    assert p["__biz"] == "MzA=="
    assert p["uin"] == "1"
    assert p["key"] == "k"
    assert p["pass_ticket"] == "pt"
    assert p["nickname"] == "鸭大情报局"
    assert p["school_id"] == 2
    assert "school_name" not in p


def test_build_account_payload_premium_omits_school_id():
    rows = [{"school_id": "", "school_name": "", "nickname": "优质大号", "source": "优质"}]
    p = build_account_payload(_account("优质大号"), rows)
    assert p is not None
    assert "school_id" not in p
    assert "school_name" not in p


def test_build_account_payload_no_match_returns_none():
    rows = [{"school_id": "2", "school_name": "中山大学", "nickname": "鸭大情报局", "source": "学校"}]
    assert build_account_payload(_account("不存在的号"), rows) is None


def test_build_account_payload_skips_inactive_or_incomplete():
    rows = [{"school_id": "2", "school_name": "中山大学", "nickname": "鸭大情报局", "source": "学校"}]
    assert build_account_payload({"name": "鸭大情报局", "credentials": {}}, rows) is None
    assert build_account_payload({"name": "鸭大情报局", "status": "expired", "credentials": {"__biz": "x", "uin": "1", "key": "k"}}, rows) is None


def test_chunk_accounts_splits_at_limit():
    payloads = [{"__biz": f"b{i}"} for i in range(120)]
    chunks = chunk_accounts(payloads, size=50)
    assert [len(c) for c in chunks] == [50, 50, 20]
    assert chunk_accounts(payloads[:30], size=50) == [payloads[:30]]


def test_default_batch_limit_is_small_for_slow_server():
    # 服务端逐条校验慢，默认批次必须足够小以避开网关 30s 超时
    from app.sync_server import BATCH_LIMIT

    assert BATCH_LIMIT == 3
    chunks = chunk_accounts([{"__biz": f"b{i}"} for i in range(10)])
    assert [len(c) for c in chunks] == [3, 3, 3, 1]


def test_build_account_payload_bad_school_id_returns_none():
    rows = [{"school_id": "abc", "school_name": "中山大学", "nickname": "鸭大情报局", "source": "学校"}]
    assert build_account_payload(_account("鸭大情报局"), rows) is None


def test_upload_credentials_batch_posts_correct_payload(monkeypatch):
    calls = {}

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def fake_post(url, *, json=None, timeout=None, headers=None, proxies=None):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        calls["headers"] = headers
        calls["proxies"] = proxies
        return FakeResp({"ok": True, "accepted": [], "failed": []})

    monkeypatch.setattr("app.sync_server.requests.post", fake_post)
    accounts = [{"__biz": "MzA==", "uin": "1", "key": "k"}]
    result = upload_credentials_batch("https://example.com/base", accounts)
    assert result == {"ok": True, "accepted": [], "failed": []}
    assert calls["url"] == "https://example.com/base/api/wechat/internal/mitm-credentials"
    assert calls["json"] == {"accounts": accounts}
    assert calls["headers"]["Content-Type"] == "application/json"
    assert calls["timeout"] == 60
    # 同步目标是公网接口，必须绕过本机抓包代理，避免 SSL 校验失败
    assert calls["proxies"] == {"http": None, "https": None}


def test_upload_credentials_batch_raises_on_http_error(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.sync_server.requests.post",
        lambda *a, **k: FakeResp(),
    )
    import pytest

    with pytest.raises(RuntimeError, match="boom"):
        upload_credentials_batch("https://example.com", [{"__biz": "x"}])
