"""GitHub release updater check for Schinza."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable

GITHUB_REPO = "Alexxxxxxxxxxxxy/schinza-wechat-certificate"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
APP_VERSION = "1.6.3"
CHECK_TIMEOUT = 12  # seconds


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    release_url: str
    body: str


def _parse_version(tag: str) -> tuple[int, ...]:
    m = re.search(r"(\d+(?:\.\d+)+)", tag or "")
    if not m:
        return (0,)
    try:
        return tuple(int(x) for x in m.group(1).split("."))
    except ValueError:
        return (0,)


def fetch_latest_release(
    timeout: int = CHECK_TIMEOUT,
) -> UpdateInfo | None:
    """Return latest release info or None if the API call fails."""
    req = urllib.request.Request(
        RELEASES_API,
        headers={
            "User-Agent": "Schinza-update-check",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tag = str(payload.get("tag_name") or "")
    if not tag:
        return None
    return UpdateInfo(
        version=tag,
        release_url=str(payload.get("html_url") or RELEASE_URL),
        body=str(payload.get("body") or "").strip(),
    )


def is_newer_than(remote_tag: str, current_version: str = APP_VERSION) -> bool:
    return _parse_version(remote_tag) > _parse_version(current_version)


def check_for_update_sync(
    *,
    current_version: str = APP_VERSION,
    timeout: int = CHECK_TIMEOUT,
) -> tuple[bool, str, UpdateInfo | None]:
    """Blocking check. Returns (is_newer, message, info)."""
    info = fetch_latest_release(timeout=timeout)
    if info is None:
        return False, "无法访问 GitHub，请检查网络后重试", None
    if is_newer_than(info.version, current_version):
        return True, f"发现新版本 {info.version}", info
    return False, f"已是最新版（{current_version}）", info


def check_update_async(
    *,
    current_version: str = APP_VERSION,
    on_result: Callable[[bool, str, UpdateInfo | None], None],
) -> None:
    """Run check in background thread; calls on_result on completion."""
    def _run() -> None:
        time.sleep(0.2)
        try:
            newer, msg, info = check_for_update_sync(current_version=current_version)
        except Exception:
            newer, msg, info = False, "检查更新失败", None
        on_result(newer, msg, info)

    threading.Thread(target=_run, name="schinza-update-check", daemon=True).start()
