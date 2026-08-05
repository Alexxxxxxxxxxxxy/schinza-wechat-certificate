"""Read WeChat MP article HTML and export (inspired by wechat-article-exporter).

Formats: html (normalized WeChat layout), markdown, txt, json.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup, Tag

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "WindowsWechat(0x63090a13) XWEB/11275"
)

ARTICLE_EXPORT_FORMATS: dict[str, str] = {
    "html": "HTML",
    "markdown": "Markdown",
    "txt": "TXT",
    "json": "JSON",
}

ARTICLE_EXPORT_LABELS = list(ARTICLE_EXPORT_FORMATS.values())


def _fully_unquote(value: str) -> str:
    s = value or ""
    for _ in range(3):
        n = unquote(s)
        if n == s:
            break
        s = n
    return s


def _html_to_text(fragment: str) -> str:
    if not fragment:
        return ""
    soup = BeautifulSoup(fragment, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _extract_publish_ts(html_text: str) -> int:
    for pattern in (
        r'var\s+ct\s*=\s*"(\d+)"',
        r'var\s+createTime\s*=\s*[\'"](\d+)[\'"]',
        r'publish_time\s*[:=]\s*[\'"]?(\d{10})',
        r'content_noencode.*?createTime\s*[:=]\s*[\'"]?(\d{10})',
    ):
        m = re.search(pattern, html_text or "", re.I | re.S)
        if m:
            try:
                ts = int(m.group(1))
                if ts > 1_000_000_000:
                    return ts
            except Exception:
                continue
    return 0


def normalize_wechat_html(raw_html: str) -> str:
    """Normalize raw MP HTML like wechat-article-exporter's normalizeHtml.

    - Prefer #js_article shell when present
    - Unhide #js_content
    - Drop ads / QR / scripts
    - Promote data-src images to src
    """
    soup = BeautifulSoup(raw_html or "", "html.parser")
    article = soup.select_one("#js_article")
    if article is None:
        # Fallback: wrap parsed body content
        content = soup.select_one("#js_content") or soup.select_one("div.rich_media_content")
        title_el = soup.select_one("#activity-name") or soup.select_one("h1.rich_media_title")
        title = title_el.get_text(strip=True) if title_el else ""
        body_inner = str(content) if content else _html_to_text(raw_html or "")
        return article_to_html_document(
            {
                "title": title or "(无标题)",
                "body_html": body_inner,
                "body_text": _html_to_text(body_inner),
                "link": "",
                "publish_at": "",
            }
        )

    content = article.select_one("#js_content")
    if content is not None and isinstance(content, Tag):
        if content.has_attr("style"):
            del content["style"]

    for sel in (
        "#js_top_ad_area",
        "#js_tags_preview_toast",
        "#content_bottom_area",
        "#js_pc_qr_code",
        "#wx_stream_article_slide_tip",
        "script",
    ):
        for node in article.select(sel):
            node.decompose()

    for img in soup.find_all("img"):
        if not isinstance(img, Tag):
            continue
        src = img.get("src") or img.get("data-src")
        if src:
            img["src"] = src

    body = soup.body
    body_cls = ""
    if body is not None and isinstance(body, Tag):
        body_cls = " ".join(body.get("class") or [])

    page = str(article)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh_CN">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
        '<meta name="referrer" content="no-referrer">\n'
        "<style>\n"
        "#page-content,#js_article,.__page_content__{max-width:667px;margin:0 auto;}\n"
        "img{max-width:100%;height:auto;}\n"
        "body{font-family:Microsoft YaHei,Segoe UI,sans-serif;line-height:1.7;"
        "color:#1a1a1a;background:#fff;padding:16px;}\n"
        "</style>\n"
        "</head>\n"
        f'<body class="{html.escape(body_cls)}">\n'
        f"{page}\n"
        "</body>\n"
        "</html>\n"
    )


def parse_wechat_article_html(
    html_text: str,
    *,
    source_url: str = "",
) -> dict[str, Any]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    title = ""
    title_el = soup.select_one("#activity-name") or soup.select_one("h1.rich_media_title")
    if title_el:
        title = title_el.get_text(strip=True)
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = title or str(og_title["content"]).strip()

    content = soup.select_one("#js_content") or soup.select_one("div.rich_media_content")
    body_html = str(content) if content else ""
    body_text = _html_to_text(body_html) if body_html else _html_to_text(html_text or "")

    if len(body_text) < 20:
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            desc = str(og_desc["content"]).strip()
            if len(desc) > len(body_text):
                body_text = desc

    publish_ts = _extract_publish_ts(html_text or "")
    publish_at = (
        datetime.fromtimestamp(publish_ts).strftime("%Y-%m-%d %H:%M")
        if publish_ts
        else ""
    )

    normalized = ""
    try:
        if soup.select_one("#js_article") or content:
            normalized = normalize_wechat_html(html_text or "")
    except Exception:
        normalized = ""

    return {
        "title": title or "(无标题)",
        "body_text": body_text,
        "body_html": body_html or body_text,
        "normalized_html": normalized,
        "link": source_url or "",
        "publish_ts": publish_ts,
        "publish_at": publish_at,
    }


def article_to_markdown(art: dict[str, Any]) -> str:
    title = str(art.get("title") or "(无标题)").strip()
    link = str(art.get("link") or "").strip()
    when = str(art.get("publish_at") or "").strip()
    body_html = str(art.get("body_html") or "")
    body = _html_fragment_to_markdown(body_html) if body_html else ""
    if not body.strip():
        body = str(art.get("body_text") or "").strip()
    lines = [f"# {title}", ""]
    if link:
        lines.append(f"来源：{link}")
    if when:
        lines.append(f"发布时间：{when}")
    if link or when:
        lines.append("")
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def _html_fragment_to_markdown(fragment: str) -> str:
    """Lightweight HTML→MD (headings, paragraphs, lists, links, images, bold/italic)."""
    if not fragment:
        return ""
    soup = BeautifulSoup(fragment, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    def walk(node: Any) -> str:
        if isinstance(node, str):
            return re.sub(r"\s+", " ", node)
        if not isinstance(node, Tag):
            return ""
        name = (node.name or "").lower()
        inner = "".join(walk(c) for c in node.children)
        if name in ("h1", "h2", "h3", "h4"):
            level = int(name[1])
            return f"\n{'#' * level} {inner.strip()}\n\n"
        if name == "p":
            return f"\n{inner.strip()}\n\n"
        if name == "br":
            return "\n"
        if name in ("strong", "b"):
            return f"**{inner.strip()}**" if inner.strip() else ""
        if name in ("em", "i"):
            return f"*{inner.strip()}*" if inner.strip() else ""
        if name == "a":
            href = node.get("href") or ""
            text = inner.strip() or href
            return f"[{text}]({href})" if href else text
        if name == "img":
            src = node.get("src") or node.get("data-src") or ""
            alt = node.get("alt") or "image"
            return f"\n![{alt}]({src})\n\n" if src else ""
        if name in ("ul", "ol"):
            items = []
            for i, li in enumerate(node.find_all("li", recursive=False), start=1):
                t = "".join(walk(c) for c in li.children).strip()
                prefix = f"{i}." if name == "ol" else "-"
                items.append(f"{prefix} {t}")
            return "\n" + "\n".join(items) + "\n\n"
        if name == "blockquote":
            quoted = "\n".join("> " + ln for ln in inner.strip().splitlines() if ln.strip())
            return f"\n{quoted}\n\n"
        if name in ("div", "section", "span", "section"):
            return inner
        return inner

    text = walk(soup)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def article_to_txt(art: dict[str, Any]) -> str:
    title = str(art.get("title") or "(无标题)").strip()
    link = str(art.get("link") or "").strip()
    when = str(art.get("publish_at") or "").strip()
    body = str(art.get("body_text") or "").strip()
    lines = [title, ""]
    if link:
        lines.append(f"来源：{link}")
    if when:
        lines.append(f"发布时间：{when}")
    if link or when:
        lines.append("")
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def article_to_json(art: dict[str, Any]) -> str:
    payload = {
        "title": art.get("title") or "(无标题)",
        "link": art.get("link") or "",
        "publish_ts": int(art.get("publish_ts") or 0),
        "publish_at": art.get("publish_at") or "",
        "body_text": art.get("body_text") or "",
        "body_html": art.get("body_html") or "",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def article_to_html_document(art: dict[str, Any]) -> str:
    normalized = str(art.get("normalized_html") or "").strip()
    if normalized and "<!DOCTYPE html>" in normalized:
        return normalized

    title = html.escape(str(art.get("title") or "(无标题)"))
    link = html.escape(str(art.get("link") or ""))
    when = html.escape(str(art.get("publish_at") or ""))
    body_html = str(art.get("body_html") or "")
    if not body_html.strip():
        body_html = f"<pre>{html.escape(str(art.get('body_text') or ''))}</pre>"
    meta_bits = []
    if link:
        meta_bits.append(f'<p class="meta">来源：<a href="{link}">{link}</a></p>')
    if when:
        meta_bits.append(f'<p class="meta">发布时间：{when}</p>')
    meta = "\n".join(meta_bits)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        f"<title>{title}</title>\n"
        "<style>\n"
        "body{font-family:Microsoft YaHei,Segoe UI,sans-serif;max-width:760px;"
        "margin:32px auto;padding:0 20px;line-height:1.7;color:#1a1a1a;}\n"
        "h1{font-size:1.6rem;margin-bottom:0.4em;}\n"
        ".meta{color:#666;font-size:0.9rem;}\n"
        "img{max-width:100%;height:auto;}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{title}</h1>\n"
        f"{meta}\n"
        f'<div class="content">{body_html}</div>\n'
        "</body>\n"
        "</html>\n"
    )


def render_article_export(art: dict[str, Any], fmt: str) -> str:
    key = (fmt or "markdown").lower().strip()
    aliases = {
        "md": "markdown",
        "markdown": "markdown",
        "html": "html",
        "txt": "txt",
        "text": "txt",
        "json": "json",
    }
    key = aliases.get(key, key)
    if key == "html":
        return article_to_html_document(art)
    if key == "markdown":
        return article_to_markdown(art)
    if key == "txt":
        return article_to_txt(art)
    if key == "json":
        return article_to_json(art)
    raise ValueError(f"不支持的导出格式: {fmt}")


def format_key_for_article_label(label: str) -> str:
    for key, lb in ARTICLE_EXPORT_FORMATS.items():
        if lb == label:
            return key
    return "markdown"


def extension_for_article_format(fmt: str) -> str:
    key = (fmt or "markdown").lower()
    if key in ("md", "markdown"):
        return "md"
    if key == "html":
        return "html"
    if key in ("txt", "text"):
        return "txt"
    if key == "json":
        return "json"
    return "md"


def fetch_article_html(
    url: str,
    *,
    cred: dict[str, Any] | None = None,
    timeout: float = 25.0,
    session: requests.Session | None = None,
) -> str:
    """Fetch article page HTML (direct to WeChat, bypass system proxy)."""
    url = (url or "").strip()
    if not url:
        raise ValueError("文章链接为空")

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://mp.weixin.qq.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    cookies: dict[str, str] = {}
    if cred:
        pt = str(cred.get("pass_ticket") or "").strip()
        uin = str(cred.get("uin") or "").strip()
        if pt:
            cookies["pass_ticket"] = _fully_unquote(pt)
        if uin:
            cookies["wxuin"] = _fully_unquote(uin)

    sess = session or requests.Session()
    sess.trust_env = False
    resp = sess.get(url, headers=headers, cookies=cookies, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def fetch_and_parse_article(
    url: str,
    *,
    cred: dict[str, Any] | None = None,
    timeout: float = 25.0,
) -> dict[str, Any]:
    html_text = fetch_article_html(url, cred=cred, timeout=timeout)
    return parse_wechat_article_html(html_text, source_url=url)
