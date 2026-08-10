"""Shared error helpers: never swallow into an empty / cryptic message."""

from __future__ import annotations

from typing import Any


def describe_exception(exc: Exception) -> str:
    """Never return an empty error message (requests exceptions often have '')."""
    msg = str(exc).strip()
    name = type(exc).__name__
    return f"{name}: {msg}" if msg else name


def wechat_error_hint(ret: Any, errmsg: str) -> str:
    """Map WeChat getmsg ret/errmsg to an actionable message.

    WeChat returns ``ret=-6, errmsg='unknownerror'`` when it flags the account /
    session as abnormal (risk control) — that is NOT a local network problem.
    """
    text = (errmsg or "").strip()
    low = text.lower()
    if "unknownerror" in low or "unknown error" in low:
        return (
            "微信风控拒绝（unknownerror）：账号/会话被识别为异常，"
            "请降低拉取频率、稍后再试；如持续出现，请更换微信账号后重新抓包"
        )
    try:
        ret_i = int(ret)
    except (TypeError, ValueError):
        ret_i = None
    if ret_i in (-3, -6):
        return (
            f"微信会话异常（ret={ret}）：凭证可能无效或已过期，"
            "请重新抓包/续约后再试"
        )
    if "freq" in low or "频繁" in text or "操作频繁" in text:
        return f"操作频繁：{text}，请稍后再试"
    if "invalid" in low or "失效" in text or "过期" in text:
        return f"凭证已失效：{text}，请重新抓包/续约"
    if text:
        return text
    return f"微信返回错误 ret={ret}"
