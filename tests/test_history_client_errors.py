"""Network-error handling for history fetch must surface real errors, not 未知错误."""

from __future__ import annotations

import json

import requests

from app import history_client
from app.history_client import (
    describe_exception,
    fetch_getmsg_page,
    fetch_history_days,
)

OK_PAYLOAD = (
    '{"ret":0,"errmsg":"ok","general_msg_list":"{\\"list\\":[]}",'
    '"can_msg_continue":0,"next_offset":0}'
)


class _FakeResp:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def json(self):
        return json.loads(self.text)


class _Session:
    """Minimal session double: records calls, raises or returns a fake response."""

    def __init__(self, exc: Exception | None = None, fail_first: int = 0) -> None:
        self._exc = exc
        self._fail_first = fail_first
        self.calls = 0

    @property
    def trust_env(self) -> bool:
        return False

    @trust_env.setter
    def trust_env(self, value: bool) -> None:
        pass

    def get(self, *args, **kwargs):
        self.calls += 1
        if self._exc is not None and self.calls <= self._fail_first:
            raise self._exc
        return _FakeResp(OK_PAYLOAD)


CRED = {"__biz": "MzA=", "uin": "1", "key": "k", "pass_ticket": "pt"}


def test_describe_exception_never_empty() -> None:
    for exc in (
        requests.Timeout(),
        requests.ConnectionError(),
        requests.exceptions.SSLError(),
        ValueError("boom"),
    ):
        text = describe_exception(exc)
        assert text
        assert type(exc).__name__ in text


def test_fetch_getmsg_page_timeout_returns_error_not_raise() -> None:
    page = fetch_getmsg_page(CRED, session=_Session(exc=requests.Timeout(), fail_first=999), retries=0)
    assert page["ok"] is False
    assert page["error"]
    assert "Timeout" in page["error"]


def test_fetch_getmsg_page_retries_then_succeeds() -> None:
    sess = _Session(exc=requests.Timeout(), fail_first=1)
    page = fetch_getmsg_page(CRED, session=sess, retries=2, retry_delay_s=0)
    assert page["ok"] is True
    assert sess.calls == 2


def test_fetch_getmsg_page_gives_up_after_retries() -> None:
    sess = _Session(exc=requests.ConnectionError(), fail_first=999)
    page = fetch_getmsg_page(CRED, session=sess, retries=1, retry_delay_s=0)
    assert page["ok"] is False
    assert page["error"]
    assert "ConnectionError" in page["error"]
    assert sess.calls == 2  # 1 + 1 retry


def test_fetch_history_days_surfaces_raised_page_error(monkeypatch) -> None:
    """Even if a page call raises, the result must carry a real, non-empty error."""

    def boom(*args, **kwargs):
        raise requests.ConnectionError()

    monkeypatch.setattr(history_client, "fetch_getmsg_page", boom)
    result = fetch_history_days(CRED, days=7, max_pages=2)
    assert result["ok"] is False
    assert result["error"]
    assert "ConnectionError" in result["error"]
    assert result["pages"] == 1


# ---------- WeChat getmsg error mapping ----------


def test_parse_getmsg_response_unknownerror_maps_to_chinese() -> None:
    """ret=-6 + errmsg='unknownerror' is WeChat risk control, not a local network issue."""
    page = history_client.parse_getmsg_response({"ret": -6, "errmsg": "unknownerror"})
    assert page["ok"] is False
    assert "unknownerror" in page["error"] or "风控" in page["error"]
    assert "风控" in page["error"]


def test_parse_getmsg_response_ret_neg3_credential_hint() -> None:
    page = history_client.parse_getmsg_response({"ret": -3, "errmsg": ""})
    assert page["ok"] is False
    assert "凭证" in page["error"]


def test_parse_getmsg_response_freq_control_hint() -> None:
    page = history_client.parse_getmsg_response({"ret": 200013, "errmsg": "freq control"})
    assert page["ok"] is False
    assert "操作频繁" in page["error"]


def test_parse_getmsg_response_other_errmsg_passthrough() -> None:
    page = history_client.parse_getmsg_response({"ret": -1, "errmsg": "some other msg"})
    assert page["ok"] is False
    assert page["error"] == "some other msg"


def test_parse_getmsg_response_ok_still_succeeds() -> None:
    page = history_client.parse_getmsg_response(
        {"ret": 0, "errmsg": "ok", "general_msg_list": '{"list":[]}'}
    )
    assert page["ok"] is True
