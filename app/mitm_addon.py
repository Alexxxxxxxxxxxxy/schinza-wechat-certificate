"""mitmproxy addon — write captured WeChat creds to inbox JSON.

Loaded by in-process DumpMaster (or ``mitmdump -s app/mitm_addon.py``).
Inbox path is read from env ``SCHINZA_CAPTURE_INBOX``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

KEYS = ("__biz", "uin", "key", "pass_ticket", "appmsg_token")
INTERESTING_HOSTS = ("mp.weixin.qq.com",)


def _inbox() -> Path:
    raw = os.environ.get("SCHINZA_CAPTURE_INBOX") or ""
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[1] / "data" / "capture_inbox.json"


def _merge_from_url(url: str, into: dict[str, str]) -> bool:
    try:
        u = urlparse(url)
    except Exception:
        return False
    if u.hostname not in INTERESTING_HOSTS:
        return False
    changed = False
    q = parse_qs(u.query)
    for k in KEYS:
        vals = q.get(k) or []
        if not vals or not vals[0]:
            continue
        v = unquote(vals[0])
        if into.get(k) != v:
            into[k] = v
            changed = True
    return changed


def _merge_from_cookie(cookie_header: str, into: dict[str, str]) -> bool:
    if not cookie_header:
        return False
    changed = False
    for part in cookie_header.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in KEYS or not v:
            continue
        v = unquote(v.strip())
        if into.get(k) != v:
            into[k] = v
            changed = True
    return changed


def _enough(cred: dict[str, str]) -> bool:
    return bool(cred.get("__biz") and cred.get("uin") and cred.get("key"))


def _url_carries_enough(url: str) -> bool:
    tmp: dict[str, str] = {}
    _merge_from_url(url, tmp)
    return _enough(tmp)


def _save(cred: dict[str, str]) -> None:
    path = _inbox()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **{k: cred.get(k, "") for k in KEYS},
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "mitm",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[schinza-capture] saved → {path}")


class CredentialCapture:
    """Accumulate WeChat MP creds; rewrite inbox whenever a complete set is seen.

    Important: do NOT one-shot ``saved=True``. Starting the proxy before
    「添加并抓包」 often sees an early hit; a one-shot flag then blocks the
    real capture after the user adds an account.
    """

    def __init__(self) -> None:
        self.cred: dict[str, str] = {}
        self._last_saved_fp: tuple[str, ...] | None = None

    def request(self, flow) -> None:  # type: ignore[no-untyped-def]
        url = flow.request.pretty_url
        changed = _merge_from_url(url, self.cred)
        try:
            cookie = flow.request.headers.get("Cookie", "") or ""
        except Exception:
            cookie = ""
        changed = _merge_from_cookie(cookie, self.cred) or changed

        if not _enough(self.cred):
            return
        # Rewrite on merge change, or when this URL carries a full set and
        # inbox was cleared (renew / new wait) — but don't spam identical writes.
        fp = tuple(self.cred.get(k, "") for k in KEYS)
        inbox_missing = not _inbox().is_file()
        should_write = False
        if changed and fp != self._last_saved_fp:
            should_write = True
        elif _url_carries_enough(url) and (inbox_missing or fp != self._last_saved_fp):
            should_write = True
        if not should_write:
            return
        print(
            "[schinza-capture] hit",
            {
                k: (v[:12] + "…" if len(v) > 12 else v)
                for k, v in self.cred.items()
            },
        )
        _save(self.cred)
        self._last_saved_fp = fp


addons = [CredentialCapture()]
