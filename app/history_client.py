"""WeChat MP history list via profile_ext?action=getmsg (same as Schinza).

Requires short-lived credentials: __biz, uin, key, pass_ticket (recommended).
"""

from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import requests

from app.history_ranges import range_text

GETMSG_URL = "https://mp.weixin.qq.com/mp/profile_ext"
REQUIRED_CRED_KEYS = ("__biz", "uin", "key")

# getmsg ``count`` is number of *push messages* (推送), not articles.
# Busy accounts may push many times/day; keep paging until date cutoff.
DEFAULT_PAGE_COUNT = 10
DEFAULT_MAX_PAGES = 100


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


def describe_exception(exc: Exception) -> str:
    """Never return an empty error message (requests exceptions often have '')."""
    msg = str(exc).strip()
    name = type(exc).__name__
    return f"{name}: {msg}" if msg else name


def _network_error(exc: Exception) -> str:
    base = describe_exception(exc)
    if isinstance(exc, requests.Timeout):
        return base + "（连接微信超时，请检查网络后重试）"
    if isinstance(exc, requests.exceptions.SSLError):
        return base + "（SSL 错误，可能是证书或代理问题）"
    return base + "（网络错误，请检查网络/代理设置后重试）"


def _clean_url(raw: str) -> str:
    s = html.unescape((raw or "").strip())
    s = s.replace("\\/", "/")
    s = s.replace("\\u0026", "&").replace("\\x26", "&")
    s = s.replace("&amp;", "&")
    if s.startswith("//"):
        s = "https:" + s
    if s.startswith("http://mp.weixin.qq.com"):
        s = "https://" + s[len("http://") :]
    return s


def _link_from_item(item: dict[str, Any]) -> str:
    for key in (
        "content_url",
        "content_url_encoded",
        "url",
        "link",
        "content_url_with_token",
    ):
        raw = item.get(key)
        if isinstance(raw, str) and raw.strip():
            return _clean_url(raw)
    return ""


def _mid_idx_sn(link: str) -> tuple[str, str, str]:
    link = _clean_url(link)
    if not link:
        return "", "", ""
    try:
        q = parse_qs(urlparse(link).query)
    except Exception:
        return "", "", ""
    mid = (q.get("mid") or q.get("appmsgid") or [""])[0]
    idx = (q.get("idx") or q.get("itemidx") or [""])[0]
    sn = (q.get("sn") or [""])[0]
    return str(mid or ""), str(idx or ""), str(sn or "")


def article_identity(
    link: str,
    *,
    title: str = "",
    publish_ts: int = 0,
    msg_id: str = "",
    ordinal: int = 0,
) -> str:
    """Stable identity for dedupe.

    Prefer mid+idx (same push, different articles). Never collapse two articles
    that only share __biz / bare /s path.
    """
    link = _clean_url(link)
    mid, idx, sn = _mid_idx_sn(link)
    if mid:
        # idx distinguishes 同一条多图文里的第 1/2/… 篇
        return f"mid:{mid}|idx:{idx or str(ordinal or 1)}|sn:{sn}"

    if link:
        try:
            u = urlparse(link)
        except Exception:
            u = None
        if u is not None:
            m = re.search(r"/s/([A-Za-z0-9_-]+)", u.path or "")
            if m:
                return f"s:{m.group(1)}"
            # Keep full URL path+query (minus fragment) — do not over-strip
            return urlunparse((u.scheme, u.netloc, u.path, "", u.query, ""))

    # Last resort: never merge different titles from the same push
    return f"msg:{msg_id}|ord:{ordinal}|ts:{publish_ts}|t:{title}"


def _item_to_row(
    item: dict[str, Any],
    publish_ts: int,
    *,
    msg_id: str = "",
    ordinal: int = 0,
) -> dict[str, Any] | None:
    title = (item.get("title") or "").strip()
    link = _link_from_item(item)
    # 头条偶发缺 link：只要有标题也保留，避免「同一天多图文只剩最后一篇」
    if not link and not title:
        return None
    if not title:
        title = "(无标题)"
    mid, idx, sn = _mid_idx_sn(link)
    return {
        "title": title,
        "link": link,
        "digest": (item.get("digest") or "").strip(),
        "cover": _clean_url(item.get("cover") or item.get("cdn_url") or ""),
        "author": (item.get("author") or "").strip(),
        "publish_ts": publish_ts,
        "publish_at": (
            datetime.fromtimestamp(publish_ts).strftime("%Y-%m-%d %H:%M")
            if publish_ts
            else ""
        ),
        "mid": mid,
        "idx": idx or str(ordinal or 1),
        "sn": sn,
        "identity": article_identity(
            link,
            title=title,
            publish_ts=publish_ts,
            msg_id=msg_id,
            ordinal=ordinal,
        ),
    }


def _iter_msg_article_items(msg: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """Yield (ordinal, item) for head + multi-app articles in one push.

    WeChat layout:
      - 第 1 篇在 app_msg_ext_info
      - 第 2..N 篇在 app_msg_ext_info.multi_app_msg_item_list
    Some payloads also put multi on the message root — include those too.
    """
    app = msg.get("app_msg_ext_info") or {}
    if not isinstance(app, dict):
        app = {}

    items: list[tuple[int, dict[str, Any]]] = []
    if app:
        # ordinal 1 = 头条
        items.append((1, app))

    multi = app.get("multi_app_msg_item_list")
    if not isinstance(multi, list):
        multi = []
    # Fallback: multi list wrongly nested at message root (seen in some scrapers)
    root_multi = msg.get("multi_app_msg_item_list")
    if isinstance(root_multi, list) and root_multi:
        multi = list(multi) + [x for x in root_multi if x not in multi]

    for i, sub in enumerate(multi):
        if isinstance(sub, dict):
            items.append((i + 2, sub))
    return items


def parse_general_msg_list(payload: dict[str, Any] | str) -> list[dict[str, Any]]:
    if isinstance(payload, str):
        payload = json.loads(payload) if payload.strip() else {}
    rows: list[dict[str, Any]] = []
    for msg in payload.get("list") or []:
        if not isinstance(msg, dict):
            continue
        comm = msg.get("comm_msg_info") or {}
        if not isinstance(comm, dict):
            comm = {}
        # type 49 = 图文；缺省时只要有 app_msg_ext_info 也尝试解析
        msg_type = comm.get("type")
        if msg_type is not None and str(msg_type) not in ("49", "49.0"):
            # 仍可能有图文扩展，不直接跳过
            pass
        publish_ts = int(comm.get("datetime") or 0)
        msg_id = str(comm.get("id") or "")

        app = msg.get("app_msg_ext_info")
        if not isinstance(app, dict) or not app:
            continue

        for ordinal, item in _iter_msg_article_items(msg):
            row = _item_to_row(
                item,
                publish_ts,
                msg_id=msg_id,
                ordinal=ordinal,
            )
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


def _get_page_with_retry(
    sess: requests.Session,
    *,
    params: dict[str, str],
    headers: dict[str, str],
    cookies: dict[str, str],
    timeout: float,
    retries: int,
    retry_delay_s: float,
) -> tuple[requests.Response | None, Exception | None]:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = sess.get(
                GETMSG_URL, params=params, headers=headers, cookies=cookies, timeout=timeout
            )
            return resp, None
        except requests.exceptions.SSLError as exc:
            # 证书类错误重试无意义：立即返回，避免反复超时
            return None, exc
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(retry_delay_s * (attempt + 1))
        except Exception as exc:  # noqa: BLE001 - other errors: surface immediately
            return None, exc
    return None, last_exc


def fetch_getmsg_page(
    cred: dict[str, Any],
    *,
    offset: int = 0,
    count: int = DEFAULT_PAGE_COUNT,
    timeout: float = 25.0,
    session: requests.Session | None = None,
    retries: int = 2,
    retry_delay_s: float = 1.0,
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
    resp, net_err = _get_page_with_retry(
        sess,
        params=params,
        headers=headers,
        cookies=cookies,
        timeout=timeout,
        retries=max(0, int(retries)),
        retry_delay_s=max(0.0, float(retry_delay_s)),
    )
    if net_err is not None:
        return {
            "ok": False,
            "error": _network_error(net_err),
            "articles": [],
            "can_continue": False,
            "next_offset": None,
        }
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


def _page_newest_ts(batch: list[dict[str, Any]]) -> int:
    newest = 0
    for a in batch:
        ts = int(a.get("publish_ts") or 0)
        if ts > newest:
            newest = ts
    return newest


def _dedupe(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for a in articles:
        mid = str(a.get("mid") or "")
        idx = str(a.get("idx") or "")
        sn = str(a.get("sn") or "")
        if mid:
            key = f"mid:{mid}|idx:{idx or '1'}|sn:{sn}"
        else:
            key = str(a.get("identity") or "") or article_identity(
                str(a.get("link") or ""),
                title=str(a.get("title") or ""),
                publish_ts=int(a.get("publish_ts") or 0),
            )
        if not key:
            key = f"t:{a.get('title')}|ts:{a.get('publish_ts')}|l:{a.get('link')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _sighting_to_article(s: dict[str, Any]) -> dict[str, Any] | None:
    link = _clean_url(str(s.get("link") or ""))
    title = str(s.get("title") or "").strip() or "(无标题)"
    if not link and title == "(无标题)":
        return None
    publish_ts = int(s.get("publish_ts") or 0)
    mid, idx, sn = _mid_idx_sn(link)
    if not mid:
        mid = str(s.get("mid") or "")
        idx = str(s.get("idx") or idx or "1")
        sn = str(s.get("sn") or sn)
    identity = str(s.get("identity") or "") or article_identity(
        link, title=title, publish_ts=publish_ts
    )
    return {
        "title": title,
        "link": link,
        "digest": str(s.get("digest") or "").strip(),
        "cover": _clean_url(str(s.get("cover") or "")),
        "author": str(s.get("author") or "").strip(),
        "publish_ts": publish_ts,
        "publish_at": str(s.get("publish_at") or "")
        or (
            datetime.fromtimestamp(publish_ts).strftime("%Y-%m-%d %H:%M")
            if publish_ts
            else ""
        ),
        "mid": mid,
        "idx": idx or "1",
        "sn": sn,
        "identity": identity,
        "source": str(s.get("source") or "sighting"),
    }


def merge_articles_with_sightings(
    base: list[dict[str, Any]],
    sightings: list[dict[str, Any]],
    *,
    cutoff_ts: int = 0,
    biz: str = "",
) -> list[dict[str, Any]]:
    """Merge getmsg articles with MITM/manual sightings (fills API gaps).

    WeChat often omits later same-day pushes from ``getmsg``. Sightings collected
    while browsing (or补录) are merged in and deduped by mid|idx|sn / identity.
    """
    rows: list[dict[str, Any]] = []
    for a in base or []:
        row = dict(a)
        row.setdefault("source", "getmsg")
        rows.append(row)

    biz = (biz or "").strip()
    for s in sightings or []:
        if biz:
            sb = str(s.get("__biz") or "").strip()
            link_biz = ""
            try:
                q = parse_qs(urlparse(_clean_url(str(s.get("link") or ""))).query)
                link_biz = unquote((q.get("__biz") or [""])[0])
            except Exception:
                link_biz = ""
            if sb and sb != biz:
                continue
            if not sb and link_biz and link_biz != biz:
                continue
        art = _sighting_to_article(s)
        if not art:
            continue
        ts = int(art.get("publish_ts") or 0)
        if cutoff_ts and ts and ts < cutoff_ts:
            continue
        rows.append(art)

    merged = _dedupe(rows)
    merged = [
        a
        for a in merged
        if not cutoff_ts
        or not int(a.get("publish_ts") or 0)
        or int(a.get("publish_ts") or 0) >= cutoff_ts
    ]
    merged.sort(key=lambda a: int(a.get("publish_ts") or 0), reverse=True)
    return merged


def fetch_history_days(
    cred: dict[str, Any],
    *,
    days: int | None = 7,
    max_pages: int = DEFAULT_MAX_PAGES,
    count: int = DEFAULT_PAGE_COUNT,
    sleep_s: float = 1.2,
    on_progress: ProgressCb | None = None,
    sightings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Paginate getmsg and keep articles with publish_ts within the last ``days``.

    ``days=None`` 表示「全部」：不过滤日期，一直翻页到没有更多（或达 max_pages）。

    Important: getmsg ``count`` is push-message count. One push may contain many
    articles (multi-appmsg). We keep paging until the whole page is older than
    the cutoff (or WeChat says no more / hit max_pages).

    ``sightings`` (MITM browse / 补录) are merged in because WeChat often omits
    later same-day pushes from getmsg alone.
    """
    cred = normalize_credentials(cred)
    ok, err = validate_credentials(cred)
    if not ok:
        return {"ok": False, "error": err, "articles": [], "pages": 0}

    cutoff: int | None = None
    if days is not None:
        days = max(1, int(days))
        cutoff = int(time.time()) - days * 86400
    articles: list[dict[str, Any]] = []
    pages = 0
    offset = 0
    sess = requests.Session()
    sess.trust_env = False
    hit_page_cap = False
    last_can_continue = False
    biz = str(cred.get("__biz") or "").strip()

    page_limit = max(1, int(max_pages))
    for i in range(page_limit):
        if on_progress:
            on_progress(f"正在拉取第 {i + 1} 页（已收录 {len(articles)} 篇）…")
        try:
            page = fetch_getmsg_page(cred, offset=offset, count=count, session=sess)
        except Exception as exc:  # noqa: BLE001 - never swallow into 未知错误
            page = {
                "ok": False,
                "error": describe_exception(exc),
                "articles": [],
                "can_continue": False,
                "next_offset": None,
            }
        pages += 1
        if not page.get("ok"):
            partial = merge_articles_with_sightings(
                articles, sightings or [], cutoff_ts=cutoff, biz=biz
            )
            return {
                "ok": False,
                "error": page.get("error") or "getmsg 失败",
                "articles": partial,
                "pages": pages,
                "days": days,
                "cutoff_ts": cutoff,
                "warning": "",
                "merged_sightings": max(0, len(partial) - len(_dedupe(articles))),
            }

        batch = page.get("articles") or []
        last_can_continue = bool(page.get("can_continue"))
        raw_msg_count = 0
        try:
            raw = page.get("raw") or {}
            gml = raw.get("general_msg_list") or ""
            if isinstance(gml, str):
                gml_obj = json.loads(gml) if gml.strip() else {}
            else:
                gml_obj = gml if isinstance(gml, dict) else {}
            raw_msg_count = len(gml_obj.get("list") or [])
        except Exception:
            raw_msg_count = len(batch)

        for a in batch:
            ts = int(a.get("publish_ts") or 0)
            if cutoff is not None and ts and ts < cutoff:
                continue
            row = dict(a)
            row.setdefault("source", "getmsg")
            articles.append(row)

        newest = _page_newest_ts(batch)
        page_fully_old = bool(batch) and newest > 0 and cutoff is not None and newest < cutoff

        if page_fully_old:
            break
        if raw_msg_count <= 0 and not batch:
            break

        nxt = page.get("next_offset")
        if nxt is None:
            nxt_i = offset + int(count)
        else:
            try:
                nxt_i = int(nxt)
            except Exception:
                break
        if nxt_i <= offset:
            break

        offset = nxt_i

        if i + 1 < page_limit:
            time.sleep(sleep_s)
        else:
            hit_page_cap = True
            last_can_continue = True

    base_n = len(_dedupe(articles))
    deduped = merge_articles_with_sightings(
        articles, sightings or [], cutoff_ts=cutoff, biz=biz
    )
    merged_extra = max(0, len(deduped) - base_n)

    warn = ""
    if hit_page_cap and last_can_continue:
        scope = range_text(days) + ("" if days is None else "内")
        warn = (
            f"已达翻页上限 {page_limit} 页，{scope}可能仍有文章未拉完，请再点一次拉取续翻。"
        )
    if merged_extra:
        extra = f"已合并补录/抓包 {merged_extra} 篇"
        warn = f"{warn} · {extra}" if warn else extra

    if on_progress:
        msg = f"完成：{range_text(days)}共 {len(deduped)} 篇（请求 {pages} 页）"
        if warn:
            msg += f" · {warn}"
        on_progress(msg)

    return {
        "ok": True,
        "error": "",
        "warning": warn,
        "articles": deduped,
        "pages": pages,
        "days": days,
        "cutoff_ts": cutoff,
        "hit_page_cap": hit_page_cap,
        "merged_sightings": merged_extra,
        "__biz": biz,
    }
