"""mitmproxy addon — write captured WeChat creds + article sightings.

Loaded by in-process DumpMaster (or ``mitmdump -s app/mitm_addon.py``).
Inbox path: env ``SCHINZA_CAPTURE_INBOX``.
Sightings path: env ``SCHINZA_SIGHTINGS``.
"""

from __future__ import annotations

import json
import os
import re
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


def _sightings_path() -> Path:
    raw = os.environ.get("SCHINZA_SIGHTINGS") or ""
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[1] / "data" / "article_sightings.json"


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


def _clean_url(raw: str) -> str:
    s = (raw or "").strip().replace("\\/", "/")
    if s.startswith("//"):
        s = "https:" + s
    if s.startswith("http://mp.weixin.qq.com"):
        s = "https://" + s[len("http://") :]
    return s.split("#")[0]


def is_article_url(url: str) -> bool:
    try:
        u = urlparse(url)
    except Exception:
        return False
    if u.hostname not in INTERESTING_HOSTS:
        return False
    path = u.path or ""
    if path.startswith("/s/") or path == "/s":
        return True
    return False


def extract_article_sighting(url: str) -> dict | None:
    """Build a minimal sighting dict from an article URL."""
    url = _clean_url(url)
    if not is_article_url(url):
        return None
    try:
        u = urlparse(url)
        q = parse_qs(u.query)
    except Exception:
        return None
    mid = (q.get("mid") or q.get("appmsgid") or [""])[0]
    idx = (q.get("idx") or q.get("itemidx") or ["1"])[0]
    sn = (q.get("sn") or [""])[0]
    biz = unquote((q.get("__biz") or [""])[0])
    short = ""
    m = re.search(r"/s/([A-Za-z0-9_-]+)", u.path or "")
    if m:
        short = m.group(1)
    if not mid and not short:
        return None
    if mid:
        identity = f"mid:{mid}|idx:{idx or '1'}|sn:{sn}"
    else:
        identity = f"s:{short}"
    return {
        "title": "",
        "link": url,
        "publish_ts": 0,
        "publish_at": "",
        "mid": mid,
        "idx": idx or "1",
        "sn": sn,
        "__biz": biz,
        "identity": identity,
        "source": "mitm",
    }


def _upsert_sighting(sighting: dict) -> None:
    path = _sightings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except Exception:
        data = {}
    rows = data.get("sightings") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        rows = []
    identity = str(sighting.get("identity") or "")
    link = str(sighting.get("link") or "")
    found = False
    for i, old in enumerate(rows):
        if not isinstance(old, dict):
            continue
        if identity and old.get("identity") == identity:
            merged = dict(old)
            for k, v in sighting.items():
                if v or k in ("source", "seen_at"):
                    if k == "title" and (not v or v == "(无标题)"):
                        continue
                    if k == "publish_ts" and int(v or 0) <= int(merged.get(k) or 0):
                        continue
                    merged[k] = v
            merged["seen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            rows[i] = merged
            found = True
            break
        if link and old.get("link") == link:
            merged = dict(old)
            merged.update({k: v for k, v in sighting.items() if v})
            merged["seen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            rows[i] = merged
            found = True
            break
    if not found:
        row = dict(sighting)
        row["seen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        rows.insert(0, row)
    if len(rows) > 5000:
        rows = rows[:5000]
    path.write_text(
        json.dumps(
            {"sightings": rows, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _parse_getmsg_articles(body: str, biz: str = "") -> list[dict]:
    """Best-effort parse getmsg JSON body into sighting rows."""
    text = (body or "").strip()
    if not text.startswith("{"):
        return []
    try:
        payload = json.loads(text)
    except Exception:
        return []
    gml = payload.get("general_msg_list") or ""
    try:
        if isinstance(gml, str):
            gml_obj = json.loads(gml) if gml.strip() else {}
        elif isinstance(gml, dict):
            gml_obj = gml
        else:
            gml_obj = {}
    except Exception:
        return []

    out: list[dict] = []
    for msg in gml_obj.get("list") or []:
        if not isinstance(msg, dict):
            continue
        comm = msg.get("comm_msg_info") or {}
        publish_ts = int(comm.get("datetime") or 0) if isinstance(comm, dict) else 0
        app = msg.get("app_msg_ext_info") or {}
        if not isinstance(app, dict) or not app:
            continue
        items = [app]
        multi = app.get("multi_app_msg_item_list")
        if isinstance(multi, list):
            items.extend([x for x in multi if isinstance(x, dict)])
        for ordinal, item in enumerate(items, start=1):
            title = str(item.get("title") or "").strip()
            link = _clean_url(
                str(
                    item.get("content_url")
                    or item.get("content_url_encoded")
                    or item.get("url")
                    or ""
                )
            )
            if not link and not title:
                continue
            try:
                q = parse_qs(urlparse(link).query)
            except Exception:
                q = {}
            mid = (q.get("mid") or q.get("appmsgid") or [""])[0]
            idx = (q.get("idx") or [str(ordinal)])[0]
            sn = (q.get("sn") or [""])[0]
            link_biz = unquote((q.get("__biz") or [""])[0]) or biz
            if mid:
                identity = f"mid:{mid}|idx:{idx or str(ordinal)}|sn:{sn}"
            else:
                identity = f"link:{link}" if link else f"t:{title}|ts:{publish_ts}"
            out.append(
                {
                    "title": title or "(无标题)",
                    "link": link,
                    "publish_ts": publish_ts,
                    "publish_at": time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(publish_ts)
                    )
                    if publish_ts
                    else "",
                    "mid": mid,
                    "idx": idx or str(ordinal),
                    "sn": sn,
                    "__biz": link_biz,
                    "identity": identity,
                    "source": "mitm_getmsg",
                    "digest": str(item.get("digest") or "").strip(),
                }
            )
    return out


def _enrich_sighting_from_html(html: str, base: dict) -> dict:
    title = ""
    m = re.search(
        r'id="activity-name"[^>]*>(.*?)</',
        html or "",
        re.I | re.S,
    )
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    if not title:
        m = re.search(
            r'property="og:title"\s+content="([^"]+)"',
            html or "",
            re.I,
        )
        if m:
            title = m.group(1).strip()
    ts = 0
    m = re.search(r'var\s+ct\s*=\s*"(\d+)"', html or "")
    if m:
        try:
            ts = int(m.group(1))
        except Exception:
            ts = 0
    out = dict(base)
    if title:
        out["title"] = title
    if ts:
        out["publish_ts"] = ts
        out["publish_at"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    return out


class CredentialCapture:
    """Accumulate WeChat MP creds; also record article URL sightings.

    Important: do NOT one-shot ``saved=True``. Starting the proxy before
    「添加并抓包」 often sees an early hit; a one-shot flag then blocks the
    real capture after the user adds an account.
    """

    def __init__(self) -> None:
        self.cred: dict[str, str] = {}
        self._last_saved_fp: tuple[str, ...] | None = None
        self._last_sighting_fp: str | None = None

    def request(self, flow) -> None:  # type: ignore[no-untyped-def]
        url = flow.request.pretty_url
        changed = _merge_from_url(url, self.cred)
        try:
            cookie = flow.request.headers.get("Cookie", "") or ""
        except Exception:
            cookie = ""
        changed = _merge_from_cookie(cookie, self.cred) or changed

        # Article URL sightings — fill getmsg gaps for same-day later pushes
        sighting = extract_article_sighting(url)
        if sighting:
            fp = str(sighting.get("identity") or sighting.get("link") or "")
            if fp and fp != self._last_sighting_fp:
                if not sighting.get("__biz") and self.cred.get("__biz"):
                    sighting["__biz"] = self.cred["__biz"]
                _upsert_sighting(sighting)
                self._last_sighting_fp = fp
                print(
                    "[schinza-capture] article sighting",
                    {
                        "title": (sighting.get("title") or "")[:20],
                        "id": (sighting.get("identity") or "")[:40],
                    },
                )

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

    def response(self, flow) -> None:  # type: ignore[no-untyped-def]
        try:
            url = flow.request.pretty_url
            host = flow.request.host
        except Exception:
            return
        if host not in INTERESTING_HOSTS:
            return

        # Capture getmsg pages scrolled in WeChat (may include pushes our
        # direct API call misses — still useful; also feeds multi-appmsg).
        if "action=getmsg" in url or ("profile_ext" in url and "getmsg" in url):
            try:
                body = flow.response.get_text(strict=False) or ""
            except Exception:
                body = ""
            biz = ""
            try:
                q = parse_qs(urlparse(url).query)
                biz = unquote((q.get("__biz") or [""])[0])
            except Exception:
                biz = self.cred.get("__biz") or ""
            for art in _parse_getmsg_articles(body, biz=biz):
                _upsert_sighting(art)
            return

        # Enrich article sighting with title / publish time from HTML
        if is_article_url(url):
            try:
                html = flow.response.get_text(strict=False) or ""
            except Exception:
                return
            base = extract_article_sighting(url)
            if not base:
                return
            if not base.get("__biz") and self.cred.get("__biz"):
                base["__biz"] = self.cred["__biz"]
            enriched = _enrich_sighting_from_html(html, base)
            if enriched.get("title") or enriched.get("publish_ts"):
                _upsert_sighting(enriched)


addons = [CredentialCapture()]
