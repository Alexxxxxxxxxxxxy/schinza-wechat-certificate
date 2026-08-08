"""Parse / validate short-lived WeChat MP client credentials."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

REQUIRED = ("__biz", "uin", "key")
OPTIONAL = ("pass_ticket", "appmsg_token", "wxtoken")
ALL_KEYS = REQUIRED + OPTIONAL

_URL_RE = re.compile(r"https?://mp\.weixin\.qq\.com/[^\s\"'<>]+", re.I)


def _fully_unquote(value: str) -> str:
    s = value or ""
    for _ in range(3):
        n = unquote(s)
        if n == s:
            break
        s = n
    return s


def extract_credentials_from_url(url: str) -> dict[str, str]:
    q = parse_qs(urlparse(url.strip()).query)
    out: dict[str, str] = {}
    for key in ALL_KEYS:
        vals = q.get(key) or []
        if vals and vals[0]:
            out[key] = _fully_unquote(vals[0].strip())
    return out


def find_mp_url(text: str) -> str | None:
    if not text:
        return None
    m = _URL_RE.search(text)
    return m.group(0) if m else None


def normalize_credentials(cred: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in ALL_KEYS:
        v = cred.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = _fully_unquote(v.strip())
    return out


def credentials_enough(cred: dict[str, Any]) -> bool:
    return all(str(cred.get(k) or "").strip() for k in REQUIRED)


def credentials_to_json(cred: dict[str, Any]) -> str:
    payload = {k: str(cred.get(k) or "") for k in ALL_KEYS if cred.get(k)}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def try_parse_credentials(text: str) -> dict[str, str] | None:
    """Accept a raw URL, JSON blob, or mixed clipboard text."""
    raw = (text or "").strip()
    if not raw:
        return None

    # JSON first
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if isinstance(data.get("credentials"), dict):
                    data = data["credentials"]
                cred = normalize_credentials(data)
                if credentials_enough(cred):
                    return cred
        except Exception:
            pass

    url = find_mp_url(raw) or (raw if "mp.weixin.qq.com" in raw else None)
    if url:
        cred = normalize_credentials(extract_credentials_from_url(url))
        if credentials_enough(cred):
            return cred
    return None
