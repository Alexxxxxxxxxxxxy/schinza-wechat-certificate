"""Schinza 开放接口同步：公众号列表 CSV 解析、凭证匹配与分批上传。"""

from __future__ import annotations

import json
from typing import Any

import requests

SOURCE_SCHOOL = "学校"
SOURCE_PREMIUM = "优质"
BATCH_LIMIT = 50
_CSV_COLUMNS = ("school_id", "school_name", "nickname", "source")


def parse_school_accounts_csv(text: str) -> list[dict[str, Any]]:
    """解析公众号列表 CSV（容忍 BOM）。返回 [{school_id, school_name, nickname, source}]。"""
    import csv
    import io

    raw = (text or "").lstrip("\ufeff")
    buf = io.StringIO(raw)
    reader = csv.reader(buf)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return []
    rows: list[dict[str, Any]] = []
    for line in reader:
        if not line or not any(cell.strip() for cell in line):
            continue
        d = dict(zip(header, [c.strip() for c in line]))
        nickname = d.get("nickname") or ""
        if not nickname:
            continue
        source = (d.get("source") or "").strip()
        source = source if source == SOURCE_PREMIUM else SOURCE_SCHOOL
        rows.append(
            {
                "school_id": (d.get("school_id") or "").strip(),
                "school_name": (d.get("school_name") or "").strip(),
                "nickname": nickname,
                "source": source,
            }
        )
    return rows


def _credential_fields(row: dict[str, Any]) -> dict[str, str]:
    cred = row.get("credentials") or {}
    return {
        k: str(cred.get(k) or "").strip()
        for k in ("__biz", "uin", "key", "pass_ticket", "appmsg_token")
        if str(cred.get(k) or "").strip()
    }


def build_account_payload(
    account: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """本地账号按 name 完全匹配列表 nickname。返回上传 payload 或 None。"""
    if account.get("status") != "active":
        return None
    cred = _credential_fields(account)
    if not (cred.get("__biz") and cred.get("uin") and cred.get("key")):
        return None
    name = (account.get("name") or "").strip()
    if not name:
        return None
    match = next((r for r in rows if (r.get("nickname") or "").strip() == name), None)
    if match is None:
        return None
    payload: dict[str, Any] = dict(cred)
    payload["nickname"] = name
    if match.get("source") == SOURCE_PREMIUM:
        return payload
    sid = str(match.get("school_id") or "").strip()
    if sid:
        try:
            payload["school_id"] = int(sid)
        except ValueError:
            return None
    else:
        sname = (match.get("school_name") or "").strip()
        if sname:
            payload["school_name"] = sname
    return payload


def chunk_accounts(
    payloads: list[dict[str, Any]],
    size: int = BATCH_LIMIT,
) -> list[list[dict[str, Any]]]:
    return [payloads[i : i + size] for i in range(0, len(payloads), size)]


def upload_credentials_batch(
    base_url: str,
    accounts: list[dict[str, Any]],
    timeout: int = 15,
) -> dict[str, Any]:
    """POST 一批凭证到开放接口，返回服务端 JSON。

    显式禁用 HTTP(S) 代理：本机抓包代理（mitmproxy）会把请求
    劫持到 127.0.0.1:8088 并用私有 CA 签名，导致 SSL 校验失败；
    同步目标为公网接口，必须直连。
    """
    base = (base_url or "").strip().rstrip("/")
    url = f"{base}/api/wechat/internal/mitm-credentials"
    resp = requests.post(
        url,
        json={"accounts": accounts},
        headers={"Content-Type": "application/json"},
        timeout=timeout,
        proxies={"http": None, "https": None},
    )
    resp.raise_for_status()
    return resp.json()
