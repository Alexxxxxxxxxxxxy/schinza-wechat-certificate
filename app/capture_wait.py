"""When captured credentials never arrive, surface a stall hint instead of spinning."""

from __future__ import annotations

STALL_AFTER_S = 20.0

MAC_STALL_HINT = (
    "仍未捕获到微信流量：请确认系统代理已指向 127.0.0.1:8088，然后完全退出并重启微信，"
    "再打开该公众号文章。若开了 Clash/Surge TUN 或增强模式，请先关掉。"
    "抓包明细见 data/capture_debug.log"
)


def should_show_capture_stall_hint(
    elapsed_s: float,
    *,
    waiting: bool,
    already_shown: bool,
    after_s: float = STALL_AFTER_S,
) -> bool:
    if already_shown or not waiting:
        return False
    return elapsed_s >= after_s
