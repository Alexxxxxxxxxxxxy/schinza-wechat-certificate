"""WeChat MP history list via profile_ext?action=getmsg (same as Schinza).

Requires short-lived credentials: __biz, uin, key, pass_ticket (recommended).
"""

from __future__ import annotations

import html
import json
import time
from datetime import datetime
from typing import Any, Callable
from urllib.parse import unquote, urlencode

import requests

GETMSG_URL = "https://mp.weixin.qq.com/mp/profile_ext"
REQUIRED_CRED_KEYS = ("__biz", "uin", "key")


def _fully_unquote(value: str) -> str:
    s = value or ""
    for _ in range(3):
        n = unquote(s)
        if n == s:
            break
        s = n
    return s


def normalize_credentials(cred: dict[str, Any]) -> dict[str, Any]:
    out = dict(cred)
    for k in ("__biz", "uin", "key", "pass_ticket", "appmsg_token", "wxtoken"):
        if k in out and isinstance(out[k], str):
            out[k] = _fully_unquote(out[k].strip())
    return out


def validate_credentials(cred: dict[str, Any]) -> tuple[bool, str]:
    missing = [k for k in REQUIRED_CRED_KEYS if not str(cred.get(k) or "").strip()]
    if missing:
        return False, f"缺少字段: {', '.join(missing)}"
    return True, ""


def _clean_url(raw: str) -> str:
    s = html.unescape((raw or "").strip())
    s = s.replace("\\/", "/")
    if s.startswith("http://mp.weixin.qq.com"):
        s = "https://" + s[len("http://") :]
    return s


def _item_to_row(item: dict[str, Any], publish_ts: int) -> dict[str, Any] | None:
    title = (item.get("title") or "").strip()
    link = _clean_url(item.get("content_url") or item.get("content_url_encoded") or "")
    if not title or not link:
        return None
    return {
        "title": title,
        "link": link,
        "digest": (item.get("digest") or "").strip(),
        "cover": _clean_url(item.get("cover") or ""),
        "author": (item.get("author") or "").strip(),
        "publish_ts": publish_ts,
        "publish_at": (
            datetime.fromtimestamp(publish_ts).strftime("%Y-%m-%d %H:%M")
            if publish_ts
            else ""
        ),
    }


def parse_general_msg_list(payload: dict[str, Any] | str) -> list[dict[str, Any]]:
    if isinstance(payload, str):
        payload = json.loads(payload) if payload.strip() else {}
    rows: list[dict[str, Any]] = []
    for msg in payload.get("list") or []:
        if not isinstance(msg, dict):
            continue
        publish_ts = int((msg.get("comm_msg_info") or {}).get("datetime") or 0)
        app = msg.get("app_msg_ext_info") or {}
        if not isinstance(app, dict):
            continue
        head = _item_to_row(app, publish_ts)
        if head:
            rows.append(head)
        for sub in app.get("multi_app_msg_item_list") or []:
            if not isinstance(sub, dict):
                continue
            row = _item_to_row(sub, publish_ts)
            if row:
                rows.append(row)
    return rows


def parse_getmsg_response(payload: dict[str, Any]) -> dict[str, Any]:
    ret = payload.get("ret")
    errmsg = str(payload.get("errmsg") or "")
    if ret not in (0, "0") and errmsg != "ok":
        return {
            "ok": False,
            "error": errmsg or f"ret={ret}",
            "articles": [],
            "can_continue": False,
            "next_offset": None,
            "raw": payload,
        }
    gml = payload.get("general_msg_list") or ""
    if isinstance(gml, dict):
        articles = parse_general_msg_list(gml)
    else:
        articles = parse_general_msg_list(str(gml))
    can = payload.get("can_msg_continue")
    return {
        "ok": True,
        "error": "",
        "articles": articles,
        "can_continue": bool(int(can)) if can is not None and str(can).isdigit() else bool(can),
        "next_offset": payload.get("next_offset"),
        "msg_count": payload.get("msg_count"),
        "raw": payload,
    }


def fetch_getmsg_page(
    cred: dict[str, Any],
    *,
    offset: int = 0,
    count: int = 10,
    timeout: float = 25.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    cred = normalize_credentials(cred)
    ok, err = validate_credentials(cred)
    if not ok:
        return {
            "ok": False,
            "error": err,
            "articles": [],
            "can_continue": False,
            "next_offset": None,
        }

    params = {
        "action": "getmsg",
        "__biz": str(cred["__biz"]).strip(),
        "f": "json",
        "offset": str(offset),
        "count": str(count),
        "is_ok": "1",
        "scene": "124",
        "uin": str(cred["uin"]).strip(),
        "key": str(cred["key"]).strip(),
        "wxtoken": str(cred.get("wxtoken") or ""),
        "devicetype": str(cred.get("devicetype") or ""),
        "clientversion": str(cred.get("clientversion") or "0"),
        "x5": "0",
    }
    if cred.get("pass_ticket"):
        params["pass_ticket"] = str(cred["pass_ticket"]).strip()
    if cred.get("appmsg_token"):
        params["appmsg_token"] = str(cred["appmsg_token"]).strip()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
            "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
            "WindowsWechat(0x63090a13) XWEB/11275"
        ),
        "Referer": (
            f"https://mp.weixin.qq.com/mp/profile_ext?action=home"
            f"&__biz={params['__biz']}&scene=124#wechat_redirect"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }
    cookies: dict[str, str] = {}
    if cred.get("pass_ticket"):
        cookies["pass_ticket"] = str(cred["pass_ticket"]).strip()
    if cred.get("uin"):
        cookies["wxuin"] = str(cred["uin"]).strip()

    sess = session or requests.Session()
    # Bypass system MITM proxy — talk to WeChat directly.
    sess.trust_env = False
    resp = sess.get(
        GETMSG_URL, params=params, headers=headers, cookies=cookies, timeout=timeout
    )
    text = resp.text.strip()
    if text.startswith("{"):
        payload = resp.json()
    else:
        try:
            payload = json.loads(text)
        except Exception:
            return {
                "ok": False,
                "error": f"非 JSON 响应 status={resp.status_code} body[:160]={text[:160]!r}",
                "articles": [],
                "can_continue": False,
                "next_offset": None,
            }
    page = parse_getmsg_response(payload)
    page["http_status"] = resp.status_code
    page["request_url"] = f"{GETMSG_URL}?{urlencode(params)}"
    return page


ProgressCb = Callable[[str], None]


def fetch_history_days(
    cred: dict[str, Any],
    *,
    days: int = 7,
    max_pages: int = 20,
    count: int = 10,
    sleep_s: float = 1.2,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Paginate getmsg and keep articles with publish_ts within the last ``days``."""
    cred = normalize_credentials(cred)
    ok, err = validate_credentials(cred)
    if not ok:
        return {"ok": False, "error": err, "articles": [], "pages": 0}

    days = max(1, int(days))
    cutoff = int(time.time()) - days * 86400
    articles: list[dict[str, Any]] = []
    pages = 0
    offset = 0
    sess = requests.Session()
    sess.trust_env = False

    for i in range(max(1, int(max_pages))):
        if on_progress:
            on_progress(f"正在拉取第 {i + 1} 页…")
        page = fetch_getmsg_page(cred, offset=offset, count=count, session=sess)
        pages += 1
        if not page.get("ok"):
            return {
                "ok": False,
                "error": page.get("error") or "getmsg 失败",
                "articles": _dedupe(articles),
                "pages": pages,
                "days": days,
                "cutoff_ts": cutoff,
            }

        batch = page.get("articles") or []
        stop = False
        for a in batch:
            ts = int(a.get("publish_ts") or 0)
            if ts and ts < cutoff:
                stop = True
                continue
            if ts >= cutoff or not ts:
                # keep undated rows only if still within early pages; prefer dated
                if ts:
                    articles.append(a)

        if stop or not page.get("can_continue"):
            break
        nxt = page.get("next_offset")
        if nxt is None:
            break
        try:
            nxt_i = int(nxt)
        except Exception:
            break
        if nxt_i == offset:
            break
        offset = nxt_i
        if i + 1 < max_pages:
            time.sleep(sleep_s)

    deduped = _dedupe(articles)
    deduped.sort(key=lambda a: int(a.get("publish_ts") or 0), reverse=True)
    if on_progress:
        on_progress(f"完成：近 {days} 天共 {len(deduped)} 篇（{pages} 页）")
    return {
        "ok": True,
        "error": "",
        "articles": deduped,
        "pages": pages,
        "days": days,
        "cutoff_ts": cutoff,
        "__biz": str(cred.get("__biz") or ""),
    }


def _dedupe(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for a in articles:
        link = a.get("link") or ""
        if not link or link in seen:
            continue
        seen.add(link)
        out.append(a)
    return out
