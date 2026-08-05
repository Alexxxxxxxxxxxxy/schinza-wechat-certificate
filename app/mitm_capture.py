"""Start/stop local mitmproxy capture in-process (thread) + system proxy."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from app.ca_setup import PROXY_HOST, PROXY_PORT, prepare_mitm_confdir

try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore


class MitmCaptureService:
    """Run DumpMaster inside a daemon thread — avoids frozen-exe SSL DLL relaunch bugs."""

    def __init__(self, app_root: Path) -> None:
        self.app_root = app_root
        self.inbox = app_root / "data" / "capture_inbox.json"
        self._lock = threading.RLock()
        self._proxy_backup: dict[str, Any] | None = None
        self._last_inbox_mtime: float = 0.0
        self._thread: threading.Thread | None = None
        self._master: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = threading.Event()
        self._start_error: str | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def clear_inbox(self) -> None:
        try:
            if self.inbox.exists():
                self.inbox.unlink()
        except Exception:
            pass
        self._last_inbox_mtime = 0.0

    def reset_inbox_cursor(self) -> None:
        """Allow re-reading the current inbox file (e.g. after binding a pending account)."""
        self._last_inbox_mtime = 0.0

    def ack_inbox(self) -> None:
        """Mark current inbox as consumed after credentials were applied."""
        try:
            if self.inbox.is_file():
                self._last_inbox_mtime = self.inbox.stat().st_mtime
        except Exception:
            pass

    def read_new_credentials(self, *, consume: bool = True) -> dict[str, str] | None:
        if not self.inbox.is_file():
            return None
        try:
            mtime = self.inbox.stat().st_mtime
        except Exception:
            return None
        if mtime <= self._last_inbox_mtime:
            return None
        try:
            data = json.loads(self.inbox.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        if not (data.get("__biz") and data.get("uin") and data.get("key")):
            return None
        if consume:
            self._last_inbox_mtime = mtime
        return {
            k: str(data.get(k) or "")
            for k in ("__biz", "uin", "key", "pass_ticket", "appmsg_token")
            if data.get(k)
        }

    def _thread_main(self, confdir: Path) -> None:
        os.environ["SCHINZA_CAPTURE_INBOX"] = str(self.inbox)
        os.environ["SCHINZA_SIGHTINGS"] = str(
            self.app_root / "data" / "article_sightings.json"
        )
        try:
            from mitmproxy.options import Options
            from mitmproxy.tools.dump import DumpMaster

            from app.mitm_addon import CredentialCapture

            opts = Options(
                listen_host=PROXY_HOST,
                listen_port=PROXY_PORT,
                confdir=str(confdir),
            )
            # block_global may be set after construct on some versions
            try:
                opts.update(block_global=False)
            except Exception:
                pass

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            async def _run() -> None:
                master = DumpMaster(
                    opts,
                    loop=loop,
                    with_termlog=False,
                    with_dumper=False,
                )
                master.addons.add(CredentialCapture())
                self._master = master
                self._running = True
                self._started.set()
                await master.run()

            loop.run_until_complete(_run())
        except Exception as exc:  # noqa: BLE001
            self._start_error = str(exc)
            self._started.set()
        finally:
            self._running = False
            self._master = None
            try:
                if self._loop and self._loop.is_running():
                    self._loop.stop()
            except Exception:
                pass
            self._loop = None

    def start(self, *, set_system_proxy: bool = True) -> tuple[bool, str]:
        with self._lock:
            if self.running:
                return True, f"抓包代理已在运行 {PROXY_HOST}:{PROXY_PORT}"

            try:
                confdir, prep_msg = prepare_mitm_confdir(self.app_root)
            except Exception as exc:  # noqa: BLE001
                return False, f"准备 CA 失败：{exc}"

            self.inbox.parent.mkdir(parents=True, exist_ok=True)
            self.clear_inbox()
            self._start_error = None
            self._started.clear()

            self._thread = threading.Thread(
                target=self._thread_main,
                args=(confdir,),
                name="schinza-mitm",
                daemon=True,
            )
            self._thread.start()

            # wait until master is up or failed
            ok_wait = self._started.wait(timeout=8.0)
            if not ok_wait:
                return False, "启动抓包超时，请重试或检查端口 8088 是否被占用"
            if self._start_error:
                err = self._start_error
                self._start_error = None
                return False, f"启动抓包失败：{err}"
            if not self.running:
                return False, "抓包线程已退出，请确认 mitmproxy-ca.pem 可用且 8088 空闲"

            proxy_msg = ""
            if set_system_proxy:
                ok, proxy_msg = self.enable_system_proxy()
                if not ok:
                    proxy_msg = f"代理已启动，但系统代理设置失败：{proxy_msg}"

            return True, (
                f"{prep_msg}\n抓包代理已启动 {PROXY_HOST}:{PROXY_PORT}。"
                + (f"\n{proxy_msg}" if proxy_msg else "\n已尝试开启系统代理。")
                + "\n请用微信桌面打开公众号文章（内置浏览器）。"
            )

    def stop(self, *, restore_proxy: bool = True) -> tuple[bool, str]:
        with self._lock:
            msg_parts: list[str] = []
            master = self._master
            if master is not None:
                try:
                    master.shutdown()
                except Exception:
                    pass
                self._master = None
            if self._thread is not None:
                self._thread.join(timeout=3.0)
                self._thread = None
                msg_parts.append("已停止抓包代理")
            self._running = False
            if restore_proxy:
                ok, m = self.restore_system_proxy()
                msg_parts.append(m if ok else f"恢复系统代理失败：{m}")
            return True, "；".join(msg_parts) if msg_parts else "代理未在运行"

    def enable_system_proxy(self) -> tuple[bool, str]:
        if winreg is None:
            return False, "非 Windows，请手动设置 HTTP 代理 127.0.0.1:8088"
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_ALL_ACCESS,
            )
            try:
                prev_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            except FileNotFoundError:
                prev_enable = 0
            try:
                prev_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            except FileNotFoundError:
                prev_server = ""
            self._proxy_backup = {"ProxyEnable": prev_enable, "ProxyServer": prev_server}
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(
                key, "ProxyServer", 0, winreg.REG_SZ, f"{PROXY_HOST}:{PROXY_PORT}"
            )
            winreg.CloseKey(key)
            self._notify_proxy_change()
            return True, f"已设置系统代理 {PROXY_HOST}:{PROXY_PORT}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def restore_system_proxy(self) -> tuple[bool, str]:
        if winreg is None or self._proxy_backup is None:
            return True, "无需恢复系统代理"
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_ALL_ACCESS,
            )
            winreg.SetValueEx(
                key,
                "ProxyEnable",
                0,
                winreg.REG_DWORD,
                int(self._proxy_backup.get("ProxyEnable") or 0),
            )
            winreg.SetValueEx(
                key,
                "ProxyServer",
                0,
                winreg.REG_SZ,
                str(self._proxy_backup.get("ProxyServer") or ""),
            )
            winreg.CloseKey(key)
            self._proxy_backup = None
            self._notify_proxy_change()
            return True, "已恢复原先系统代理设置"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    @staticmethod
    def _notify_proxy_change() -> None:
        try:
            import ctypes

            internet_set_option = ctypes.windll.Wininet.InternetSetOptionW  # type: ignore[attr-defined]
            internet_set_option(0, 39, 0, 0)
            internet_set_option(0, 37, 0, 0)
        except Exception:
            pass
