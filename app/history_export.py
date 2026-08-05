"""Export fetched WeChat history articles to multiple text formats."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# (menu label, file extension, mime-ish key)
EXPORT_FORMATS: list[tuple[str, str, str]] = [
    ("JSON", "json", "json"),
    ("CSV（Excel）", "csv", "csv"),
    ("TSV", "tsv", "tsv"),
    ("Markdown", "md", "markdown"),
    ("纯链接 TXT", "txt", "links"),
    ("标题+链接 TXT", "txt", "title_links"),
]

FORMAT_LABELS = [f[0] for f in EXPORT_FORMATS]


def format_key_for_label(label: str) -> str:
    for lb, _ext, key in EXPORT_FORMATS:
        if lb == label:
            return key
    return "json"


def extension_for_label(label: str) -> str:
    for lb, ext, _key in EXPORT_FORMATS:
        if lb == label:
            return ext
    return "json"


def _rows(articles: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i, a in enumerate(articles, start=1):
        out.append(
            {
                "index": str(i),
                "title": str(a.get("title") or ""),
                "link": str(a.get("link") or ""),
                "publish_at": str(a.get("publish_at") or ""),
                "publish_ts": str(a.get("publish_ts") or ""),
                "digest": str(a.get("digest") or ""),
                "author": str(a.get("author") or ""),
                "cover": str(a.get("cover") or ""),
            }
        )
    return out


def render_export(
    articles: list[dict[str, Any]],
    *,
    fmt: str,
    account_name: str = "",
    days: int = 7,
) -> str:
    """Return file contents (text) for the given format key."""
    fmt = (fmt or "json").lower()
    rows = _rows(articles)
    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if fmt == "json":
        payload = {
            "account": account_name,
            "days": days,
            "count": len(articles),
            "exported_at": exported_at,
            "articles": articles,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if fmt == "csv":
        buf = io.StringIO()
        # UTF-8 BOM so Excel opens Chinese correctly
        buf.write("\ufeff")
        writer = csv.DictWriter(
            buf,
            fieldnames=[
                "index",
                "title",
                "link",
                "publish_at",
                "digest",
                "author",
                "cover",
            ],
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    if fmt == "tsv":
        buf = io.StringIO()
        buf.write("\ufeff")
        writer = csv.DictWriter(
            buf,
            fieldnames=["index", "title", "link", "publish_at", "digest", "author"],
            extrasaction="ignore",
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    if fmt == "markdown":
        lines = [
            f"# {account_name or '公众号'} · 近 {days} 天历史文章",
            "",
            f"> 导出时间：{exported_at} · 共 {len(articles)} 篇",
            "",
        ]
        for r in rows:
            title = r["title"] or "(无标题)"
            when = f" `{r['publish_at']}`" if r["publish_at"] else ""
            lines.append(f"- [{title}]({r['link']}){when}")
            if r["digest"]:
                lines.append(f"  - {r['digest']}")
        lines.append("")
        return "\n".join(lines)

    if fmt == "links":
        return "\n".join(r["link"] for r in rows if r["link"]) + ("\n" if rows else "")

    if fmt == "title_links":
        lines = []
        for r in rows:
            title = r["title"] or "(无标题)"
            when = f" [{r['publish_at']}]" if r["publish_at"] else ""
            lines.append(f"{title}{when}")
            lines.append(r["link"])
            lines.append("")
        return "\n".join(lines).rstrip() + ("\n" if lines else "")

    raise ValueError(f"不支持的导出格式: {fmt}")


def default_export_filename(
    *,
    account_name: str,
    days: int,
    ext: str,
) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (account_name or "history"))
    safe = safe.strip("_") or "history"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe}_{days}d_{stamp}.{ext}"


def write_export(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)
    return path
