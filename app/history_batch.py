"""Queue history fetches across accounts (one at a time)."""

from __future__ import annotations

import random
from typing import Any, Callable

from app.history_client import classify_stopped_reason, fetch_history_days, validate_credentials

ProgressCb = Callable[[int, int, str, str], None]
FetchOne = Callable[..., dict[str, Any]]


def _status_from_result(result: dict[str, Any]) -> str:
    reason = str(result.get("stopped_reason") or "")
    if reason == "cancelled" or result.get("cancelled"):
        return "cancelled"
    if reason == "rate_limited":
        return "rate_limited"
    if reason == "expired":
        return "expired"
    if reason == "completed" and result.get("ok"):
        return "completed"
    return "failed"


def _empty_group(
    account: dict[str, Any],
    *,
    status: str,
    error: str,
    stopped_reason: str,
) -> dict[str, Any]:
    return {
        "account_id": str(account.get("id") or ""),
        "name": str(account.get("name") or "未命名公众号"),
        "articles": [],
        "pages": 0,
        "status": status,
        "error": error,
        "stopped_reason": stopped_reason,
    }


def fetch_history_batch(
    accounts: list[dict[str, Any]],
    *,
    days: int | None = 7,
    start_ts: int | None = None,
    end_ts: int | None = None,
    on_progress: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
    fetch_one: FetchOne | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    between_s: tuple[float, float] = (6.0, 10.0),
    extra_after_rate_limit_s: float = 15.0,
    sightings_for: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    worker = fetch_one or fetch_history_days
    pause = sleep_fn or (lambda s: __import__("time").sleep(s))
    groups: list[dict[str, Any]] = []
    cancelled = False
    prev_reason = ""
    total = len(accounts)

    for idx, account in enumerate(accounts):
        name = str(account.get("name") or "未命名公众号")

        # gap → cancel check → fetch (do not skip account 0 before any group)
        if idx > 0 and not (should_cancel and should_cancel()):
            lo, hi = between_s
            delay = random.uniform(min(lo, hi), max(lo, hi))
            if prev_reason == "rate_limited":
                delay += max(0.0, extra_after_rate_limit_s)
            if delay > 0:
                pause(delay)

        if should_cancel and should_cancel() and groups:
            cancelled = True
            for rest in accounts[idx:]:
                groups.append(
                    _empty_group(
                        rest,
                        status="cancelled",
                        error="已取消",
                        stopped_reason="cancelled",
                    )
                )
            break

        cred = dict(account.get("credentials") or {})
        active = account.get("active", True)
        ok_cred, cred_err = validate_credentials(cred)
        if not active or not ok_cred:
            group = _empty_group(
                account,
                status="expired",
                error=cred_err or "凭证过期，请续约",
                stopped_reason="expired",
            )
            groups.append(group)
            prev_reason = "expired"
            continue

        def _page_progress(msg: str, _idx=idx, _name=name) -> None:
            if on_progress:
                on_progress(_idx + 1, total, _name, msg)

        biz = str(cred.get("__biz") or "")
        sightings = sightings_for(biz) if sightings_for else None
        result = worker(
            cred,
            days=days,
            start_ts=start_ts,
            end_ts=end_ts,
            on_progress=_page_progress,
            should_cancel=should_cancel,
            sightings=sightings,
        )
        if result.get("cancelled"):
            cancelled = True
        reason = str(
            result.get("stopped_reason")
            or classify_stopped_reason(
                str(result.get("error") or ""),
                cancelled=bool(result.get("cancelled")),
                ok=bool(result.get("ok")),
            )
        )
        status = _status_from_result({**result, "stopped_reason": reason})
        groups.append(
            {
                "account_id": str(account.get("id") or ""),
                "name": name,
                "articles": list(result.get("articles") or []),
                "pages": int(result.get("pages") or 0),
                "status": status,
                "error": str(result.get("error") or ""),
                "stopped_reason": reason,
            }
        )
        prev_reason = reason
        if cancelled:
            for rest in accounts[idx + 1 :]:
                groups.append(
                    _empty_group(
                        rest,
                        status="cancelled",
                        error="已取消",
                        stopped_reason="cancelled",
                    )
                )
            break

    summary = {
        "completed": 0,
        "rate_limited": 0,
        "expired": 0,
        "failed": 0,
        "cancelled": 0,
        "articles": 0,
    }
    for g in groups:
        st = str(g.get("status") or "failed")
        if st in summary:
            summary[st] += 1
        else:
            summary["failed"] += 1
        summary["articles"] += len(g.get("articles") or [])

    return {
        "ok": True,
        "cancelled": cancelled,
        "groups": groups,
        "summary": summary,
    }
