"""Start/stop local mitmproxy capture in-process (thread) + system proxy."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from app.ca_setup import PROXY_HOST, PROXY_PORT, prepare_mitm_confdir

try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore


# ── macOS system-proxy helpers (networksetup / scutil) ───────────────

def _mac_default_service() -> str | None:
    """Return the networksetup service name bound to the default route (e.g. 'Wi-Fi')."""
    try:
        out = subprocess.check_output(["route", "-n", "get", "default"], text=True)
    except Exception:
        return None
    dev: str | None = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("interface:"):
            dev = line.split(":", 1)[1].strip()
    if not dev:
        return None
    try:
        hp = subprocess.check_output(
            ["networksetup", "-listallhardwareports"], text=True
        )
    except Exception:
        return None
    svc: str | None = None
    cur: str | None = None
    for line in hp.splitlines():
        line = line.strip()
        if line.startswith("Hardware Port:"):
            cur = line.split(":", 1)[1].strip()
        elif line.startswith("Device:") and line.split(":", 1)[1].strip() == dev:
            svc = cur
    return svc


def _mac_read_proxy(svc: str, kind: str) -> dict[str, object]:
    """kind: 'web' or 'secure'. Returns {enabled, server, port} of current settings."""
    cmd = f"-get{'securewebproxy' if kind == 'secure' else 'webproxy'}"
    try:
        out = subprocess.check_output(["networksetup", cmd, svc], text=True)
    except Exception:
        return {"enabled": False}
    state: dict[str, object] = {"enabled": False}
    for line in out.splitlines():
        k, _, v = line.partition(":")
        k = k.strip().lower()
        v = v.strip()
        if k == "enabled":
            state["enabled"] = v.lower() in ("yes", "true", "1")
        elif k == "server":
            state["server"] = v
        elif k == "port":
            try:
                state["port"] = int(v)
            except ValueError:
                pass
    return state


class MitmCaptureService:
    """Run DumpMaster inside a daemon thread — avoids frozen-exe SSL DLL relaunch bugs."""

    def __init__(self, app_root: Path) -> None:
        self.app_root = app_root
        self.inbox = app_root / "data" / "capture_inbox.jsonl"
        self._lock = threading.RLock()
        self._proxy_backup: dict[str, Any] | None = None
        self._mac_proxy_backup: dict[str, dict[str, object]] | None = None
        self._inbox_offset: int = 0
        self._thread: threading.Thread | None = None
        self._master: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = threading.Event()
        self._start_error: str | None = None
        self._running = False
        self._capture_addon: Any = None

    @property
    def running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def clear_inbox(self) -> None:
        try:
            if self.inbox.exists():
                self.inbox.unlink()
        except Exception:
            pass
        self._inbox_offset = 0

    def reset_capture_state(self) -> None:
        """Clear inbox + in-memory merge so renew waits for fresh WeChat traffic."""
        self.clear_inbox()
        addon = self._capture_addon
        if addon is not None and hasattr(addon, "reset_merge_state"):
            try:
                addon.reset_merge_state()
            except Exception:
                pass

    def reset_inbox_cursor(self) -> None:
        """Allow re-reading the current inbox file (e.g. after binding a pending account)."""
        self._inbox_offset = 0

    def ack_inbox(self) -> None:
        """Mark current inbox as consumed after credentials were applied."""
        try:
            if self.inbox.is_file():
                self._inbox_offset = self.inbox.stat().st_size
        except Exception:
            pass

    def read_new_credentials(self, *, consume: bool = True) -> list[dict[str, str]]:
        """Read all new credential entries from the JSONL inbox.

        The addon APPENDS one JSON object per line, so a burst of captures
        (multi-window renew) is never lost to last-write-wins.
        """
        if not self.inbox.is_file():
            return []
        try:
            size = self.inbox.stat().st_size
        except Exception:
            return []
        if size <= self._inbox_offset:
            return []
        try:
            with self.inbox.open("r", encoding="utf-8") as fh:
                fh.seek(self._inbox_offset)
                raw_lines = fh.readlines()
        except Exception:
            return []
        creds: list[dict[str, str]] = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if not (data.get("__biz") and data.get("uin") and data.get("key")):
                continue
            creds.append(
                {
                    k: str(data.get(k) or "")
                    for k in ("__biz", "uin", "key", "pass_ticket", "appmsg_token")
                    if data.get(k)
                }
            )
        if consume:
            self._inbox_offset = size
        return creds

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
                addon = CredentialCapture()
                self._capture_addon = addon
                master.addons.add(addon)
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

    def _mac_set_system_proxy(self, enable: bool) -> tuple[bool, str]:
        """Set/restore macOS HTTP+HTTPS proxy for the active network service."""
        svc = _mac_default_service()
        if not svc:
            return False, "无法识别当前网络服务，请手动设置系统代理 127.0.0.1:8088"
        try:
            if enable:
                if self._mac_proxy_backup is None:
                    self._mac_proxy_backup = {
                        "web": _mac_read_proxy(svc, "web"),
                        "secure": _mac_read_proxy(svc, "secure"),
                    }
                for kind in ("web", "secure"):
                    setter = "setsecurewebproxy" if kind == "secure" else "setwebproxy"
                    subprocess.run(
                        ["networksetup", setter, svc, PROXY_HOST, str(PROXY_PORT)],
                        check=True, capture_output=True, text=True,
                    )
                for kind in ("web", "secure"):
                    stater = "setsecurewebproxystate" if kind == "secure" else "setwebproxystate"
                    subprocess.run(
                        ["networksetup", stater, svc, "on"],
                        check=True, capture_output=True, text=True,
                    )
                return True, (
                    f"已设置系统代理（{svc}）→ 127.0.0.1:8088。"
                    "请重启微信 Mac（部分版本不会自动跟随系统代理）再打开文章抓包。"
                )
            # restore
            backup, self._mac_proxy_backup = self._mac_proxy_backup, None
            if backup:
                for kind in ("web", "secure"):
                    st = backup.get(kind) or {}
                    setter = "setsecurewebproxy" if kind == "secure" else "setwebproxy"
                    stater = "setsecurewebproxystate" if kind == "secure" else "setwebproxystate"
                    if st.get("server"):
                        subprocess.run(
                            ["networksetup", setter, svc, str(st["server"]), str(st.get("port") or 80)],
                            check=True, capture_output=True, text=True,
                        )
                    subprocess.run(
                        ["networksetup", stater, svc, "on" if st.get("enabled") else "off"],
                        check=True, capture_output=True, text=True,
                    )
            else:
                for stater in ("setwebproxystate", "setsecurewebproxystate"):
                    subprocess.run(
                        ["networksetup", stater, svc, "off"],
                        check=True, capture_output=True, text=True,
                    )
            return True, "已恢复系统代理设置（macOS）"
        except subprocess.CalledProcessError as exc:
            return (
                False,
                "设置 macOS 系统代理需要管理员权限，networksetup 执行失败："
                f"{exc.stderr or exc}\n"
                "可手动设置：系统设置 → 网络 → 详细信息 → 代理 → 勾选网页代理/安全网页代理，"
                "服务器 127.0.0.1 端口 8088，然后重启微信。",
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"设置系统代理异常：{exc}"

    def enable_system_proxy(self) -> tuple[bool, str]:
        if sys.platform == "darwin":
            return self._mac_set_system_proxy(True)
        if winreg is None:
            return False, "非 Windows/macOS，请手动设置 HTTP 代理 127.0.0.1:8088"
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
        if sys.platform == "darwin":
            return self._mac_set_system_proxy(False)
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
