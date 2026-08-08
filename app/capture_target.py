"""Route captured WeChat credentials to the correct local account by __biz."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlparse

Kind = Literal["pending", "other_account", "unknown"]


def _fully_unquote(value: str) -> str:
    s = value or ""
    for _ in range(3):
        n = unquote(s)
        if n == s:
            break
        s = n
    return s.strip()


def _biz_from_url(url: str) -> str:
    if not url or "mp.weixin.qq.com" not in url:
        return ""
    q = parse_qs(urlparse(url.strip()).query)
    vals = q.get("__biz") or []
    if vals and vals[0]:
        return _fully_unquote(vals[0])
    return ""


def expected_biz(row: dict[str, Any]) -> str:
    biz = _fully_unquote(str(row.get("biz") or ""))
    if biz:
        return biz
    cred = row.get("credentials") or {}
    if isinstance(cred, dict):
        c = _fully_unquote(str(cred.get("__biz") or ""))
        if c:
            return c
    return _biz_from_url(str(row.get("article_url") or ""))


@dataclass(frozen=True)
class ResolveResult:
    kind: Kind
    account_id: str | None
    target_name: str = ""
    pending_name: str = ""


def _name(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return str(row.get("name") or "")


def resolve_capture_target(
    *,
    accounts: list[dict[str, Any]],
    pending_id: str | None,
    cred_biz: str,
) -> ResolveResult:
    cred_biz = _fully_unquote(cred_biz)
    by_id = {str(r["id"]): r for r in accounts}
    pending = by_id.get(str(pending_id)) if pending_id else None
    pending_name = _name(pending)

    if not cred_biz:
        return ResolveResult("unknown", None, pending_name=pending_name)

    # Prefer any account that already owns this biz
    owner = None
    for row in accounts:
        if expected_biz(row) == cred_biz:
            owner = row
            break

    if owner is not None:
        oid = str(owner["id"])
        if pending_id and oid == str(pending_id):
            return ResolveResult(
                "pending", oid, target_name=_name(owner), pending_name=pending_name
            )
        if pending_id and oid != str(pending_id):
            return ResolveResult(
                "other_account",
                oid,
                target_name=_name(owner),
                pending_name=pending_name,
            )
        # No pending — still apply to owner
        return ResolveResult(
            "other_account", oid, target_name=_name(owner), pending_name=""
        )

    # Unclaimed biz: legacy pending with no expected biz may claim it
    if pending is not None and not expected_biz(pending):
        return ResolveResult(
            "pending",
            str(pending["id"]),
            target_name=pending_name,
            pending_name=pending_name,
        )

    return ResolveResult("unknown", None, pending_name=pending_name)
