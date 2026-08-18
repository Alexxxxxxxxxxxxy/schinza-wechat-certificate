"""Pure helpers for the History-tab batch UI."""

from __future__ import annotations

from typing import Any


def default_selected_ids(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if not row.get("active", True):
            continue
        cred = row.get("credentials") or {}
        if cred.get("__biz") and cred.get("uin") and cred.get("key"):
            out.append(str(row.get("id") or ""))
    return [i for i in out if i]


def group_status_label(status: str, article_count: int, error: str = "") -> str:
    if status == "completed":
        return "完成"
    if status == "rate_limited":
        return f"被风控跳过，已保留 {int(article_count)} 篇"
    if status == "expired":
        return "凭证过期，请续约"
    if status == "cancelled":
        return "已取消"
    err = (error or "").strip()
    return f"失败：{err}" if err else "失败"


def group_status_color_key(status: str) -> str:
    return {
        "completed": "ok",
        "rate_limited": "warn",
        "expired": "muted",
        "cancelled": "muted",
        "failed": "danger",
    }.get(status, "muted")


def format_batch_progress(index: int, total: int, name: str, page_msg: str) -> str:
    return f"{int(index)}/{int(total)} 「{name}」{page_msg}"


def format_batch_summary(summary: dict[str, int]) -> str:
    parts: list[str] = []
    mapping = (
        ("completed", "完成"),
        ("rate_limited", "风控跳过"),
        ("expired", "过期"),
        ("failed", "失败"),
        ("cancelled", "取消"),
    )
    for key, label in mapping:
        n = int(summary.get(key) or 0)
        if n:
            parts.append(f"{label} {n}")
    parts.append(f"共 {int(summary.get('articles') or 0)} 篇")
    return " · ".join(parts)
