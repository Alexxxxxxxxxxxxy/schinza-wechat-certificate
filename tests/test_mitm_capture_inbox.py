"""Inbox JSONL queue: multiple captures in a burst must all be consumed (no last-write-wins)."""

from __future__ import annotations

import json

from app.mitm_capture import MitmCaptureService


def _write(tmp_path, lines) -> None:
    svc = MitmCaptureService(tmp_path)
    svc.inbox.parent.mkdir(parents=True, exist_ok=True)
    with svc.inbox.open("w", encoding="utf-8") as fh:
        for d in lines:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    return svc


def test_read_new_credentials_returns_all_entries(tmp_path) -> None:
    svc = _write(
        tmp_path,
        [
            {"__biz": "A", "uin": "1", "key": "KA", "pass_ticket": "PA"},
            {"__biz": "B", "uin": "2", "key": "KB", "pass_ticket": "PB"},
        ],
    )
    creds = svc.read_new_credentials(consume=True)
    assert len(creds) == 2
    assert creds[0]["__biz"] == "A"
    assert creds[1]["__biz"] == "B"


def test_ack_advances_cursor(tmp_path) -> None:
    svc = _write(tmp_path, [{"__biz": "A", "uin": "1", "key": "KA"}])
    assert svc.read_new_credentials(consume=False) == [{"__biz": "A", "uin": "1", "key": "KA"}]
    svc.ack_inbox()
    assert svc.read_new_credentials(consume=False) == []


def test_new_entries_after_ack_are_read(tmp_path) -> None:
    svc = _write(tmp_path, [{"__biz": "A", "uin": "1", "key": "KA"}])
    assert len(svc.read_new_credentials(consume=True)) == 1
    with svc.inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"__biz": "B", "uin": "2", "key": "KB"}) + "\n")
    creds = svc.read_new_credentials(consume=True)
    assert len(creds) == 1
    assert creds[0]["__biz"] == "B"


def test_incomplete_entries_skipped(tmp_path) -> None:
    svc = _write(tmp_path, [{"__biz": "A", "uin": "1"}])  # no key
    assert svc.read_new_credentials(consume=True) == []
