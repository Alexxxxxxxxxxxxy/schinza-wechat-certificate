"""CustomTkinter desktop UI for Schinza certificate helper."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

import customtkinter as ctk
import pyperclip

from app.ca_setup import PROXY_HOST, PROXY_PORT, install_ca_windows, open_p12_in_explorer
from app.clipboard_watch import ClipboardWatcher
from app.credentials import (
    credentials_to_json,
    extract_credentials_from_url,
    try_parse_credentials,
)
from app.mitm_capture import MitmCaptureService
from app.store import TTL_MINUTES, AccountStore

# Ink / jade theme — avoid purple / cream AI defaults
COLORS = {
    "bg": "#12161c",
    "panel": "#1a212b",
    "card": "#222b38",
    "border": "#2e3a4a",
    "text": "#e8eef6",
    "muted": "#8b9bb0",
    "accent": "#3db89a",
    "accent_hover": "#4fd0af",
    "warn": "#e0a35c",
    "danger": "#d46a6a",
    "ok": "#5ecf9a",
}


def _fmt_remain(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class AccountCard(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        app: "CertificateApp",
        account: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["card"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
            **kwargs,
        )
        self.app = app
        self.account_id = str(account["id"])
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        top.grid_columnconfigure(0, weight=1)

        self.name_lbl = ctk.CTkLabel(
            top,
            text=account.get("name") or "未命名",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=16, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        )
        self.name_lbl.grid(row=0, column=0, sticky="w")

        self.timer_lbl = ctk.CTkLabel(
            top,
            text="",
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color=COLORS["accent"],
            anchor="e",
        )
        self.timer_lbl.grid(row=0, column=1, sticky="e", padx=(12, 0))

        self.meta_lbl = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
        )
        self.meta_lbl.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="e", padx=16, pady=(0, 14))

        self.copy_btn = ctk.CTkButton(
            actions,
            text="复制凭证",
            width=96,
            height=32,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#0b1412",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=lambda: self.app.copy_credentials(self.account_id),
        )
        self.copy_btn.pack(side="left", padx=(0, 8))

        self.renew_btn = ctk.CTkButton(
            actions,
            text="续约",
            width=72,
            height=32,
            corner_radius=10,
            fg_color=COLORS["warn"],
            hover_color="#ebab6e",
            text_color="#1a1208",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=lambda: self.app.renew_account(self.account_id),
        )
        self.renew_btn.pack(side="left", padx=(0, 8))

        self.open_btn = ctk.CTkButton(
            actions,
            text="打开文章",
            width=88,
            height=32,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=lambda: self.app.open_article(self.account_id),
        )
        self.open_btn.pack(side="left", padx=(0, 8))

        self.del_btn = ctk.CTkButton(
            actions,
            text="删除",
            width=64,
            height=32,
            corner_radius=10,
            fg_color="transparent",
            border_width=1,
            border_color=COLORS["danger"],
            hover_color="#3a2222",
            text_color=COLORS["danger"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=lambda: self.app.delete_account(self.account_id),
        )
        self.del_btn.pack(side="left")

        self.refresh(account)

    def refresh(self, account: dict[str, Any]) -> None:
        status = account.get("status") or "awaiting"
        remain = self.app.store.remaining_seconds(self.account_id)
        biz = (account.get("credentials") or {}).get("__biz") or account.get("biz") or "—"
        url = (account.get("article_url") or "")[:56]

        if status == "active" and remain > 0:
            self.timer_lbl.configure(text=_fmt_remain(remain), text_color=COLORS["ok"])
            self.meta_lbl.configure(text=f"有效 · __biz={biz}\n{url}")
            self.copy_btn.configure(state="normal")
            self.renew_btn.configure(state="disabled")
        elif status == "awaiting":
            self.timer_lbl.configure(text="等待凭证", text_color=COLORS["warn"])
            self.meta_lbl.configure(
                text="等待 MITM 抓包 · 请在微信桌面打开该号任意一篇文章\n" + url
            )
            self.copy_btn.configure(state="disabled")
            self.renew_btn.configure(state="disabled")
        else:
            self.timer_lbl.configure(text="已过期", text_color=COLORS["danger"])
            self.meta_lbl.configure(
                text=f"点击续约后，在微信里再打开任意一篇文章刷新凭证 · __biz={biz}\n{url}"
            )
            self.copy_btn.configure(state="disabled")
            self.renew_btn.configure(state="normal")


class CertificateApp(ctk.CTk):
    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir = root_dir
        self.store = AccountStore(root_dir / "data" / "accounts.json")
        self._pending_capture_id: str | None = None
        self._cards: dict[str, AccountCard] = {}
        self._rebuild_job: str | None = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Schinza 凭证助手")
        self.geometry("960x820")
        self.minsize(860, 720)
        self.configure(fg_color=COLORS["bg"])

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.mitm = MitmCaptureService(root_dir)

        self._build_header()
        self._build_mitm_panel()
        self._build_add_form()
        self._build_list()
        self._build_footer()

        self.watcher = ClipboardWatcher(self._on_clipboard_credentials)
        self.watcher.start()

        self.store.on_change(self._schedule_rebuild)
        self._rebuild_list()
        self.after(500, self._tick)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="Schinza 凭证助手",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=22, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(18, 2))

        sub = ctk.CTkLabel(
            header,
            text=f"本地捕获公众号短暂凭证 · 有效期 {TTL_MINUTES} 分钟 · 到期可续约",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            text_color=COLORS["muted"],
            anchor="w",
        )
        sub.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

    def _build_mitm_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["panel"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        panel.grid(row=1, column=0, sticky="ew", padx=20, pady=(16, 4))
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="① 首次使用：安装抓包证书（MITM CA）",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            panel,
            text=(
                "微信桌面内置浏览器的 uin/key/pass_ticket 只能通过本机 MITM 截取。"
                f"程序会启动本地代理 {PROXY_HOST}:{PROXY_PORT}，并使用随包附带的 mitmproxy-ca-cert.p12。"
                "每人只需安装一次 CA，然后重启微信。"
            ),
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=820,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))

        btns = ctk.CTkFrame(panel, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 8))

        ctk.CTkButton(
            btns,
            text="安装 CA 证书",
            width=120,
            height=32,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#0b1412",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=self.install_ca,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btns,
            text="打开证书文件",
            width=120,
            height=32,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.reveal_ca_file,
        ).pack(side="left", padx=(0, 8))

        self.proxy_btn = ctk.CTkButton(
            btns,
            text="手动启停代理",
            width=120,
            height=32,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=self.toggle_proxy,
        )
        self.proxy_btn.pack(side="left", padx=(0, 8))

        self.proxy_lbl = ctk.CTkLabel(
            panel,
            text="代理未启动 · 请优先用下方「添加并抓包」（会自动启动代理）",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=820,
        )
        self.proxy_lbl.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 14))

    def _build_add_form(self) -> None:
        form = ctk.CTkFrame(
            self,
            fg_color=COLORS["panel"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        form.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 8))
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            form,
            text="添加公众号",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(14, 8))

        ctk.CTkLabel(
            form,
            text="名称",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
        ).grid(row=1, column=0, sticky="w", padx=(18, 8), pady=6)

        self.name_entry = ctk.CTkEntry(
            form,
            placeholder_text="例如：数模加油站",
            height=36,
            corner_radius=10,
            border_color=COLORS["border"],
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
        )
        self.name_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 18), pady=6)

        ctk.CTkLabel(
            form,
            text="文章链接",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
        ).grid(row=2, column=0, sticky="w", padx=(18, 8), pady=6)

        self.url_entry = ctk.CTkEntry(
            form,
            placeholder_text="该公众号任意一篇文章链接 https://mp.weixin.qq.com/s/...",
            height=36,
            corner_radius=10,
            border_color=COLORS["border"],
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
        )
        self.url_entry.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=6)

        self.add_btn = ctk.CTkButton(
            form,
            text="添加并抓包",
            width=120,
            height=36,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#0b1412",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=self.add_account,
        )
        self.add_btn.grid(row=2, column=2, sticky="e", padx=(0, 18), pady=6)

        paste_row = ctk.CTkFrame(form, fg_color="transparent")
        paste_row.grid(row=3, column=0, columnspan=3, sticky="ew", padx=18, pady=(4, 14))

        self.status_lbl = ctk.CTkLabel(
            paste_row,
            text=(
                "推荐流程：安装 CA → 填写名称与文章链接 →「添加并抓包」→ "
                "再在微信桌面打开该公众号任意一篇文章（勿先空点代理再开文章）。"
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self.status_lbl.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            paste_row,
            text="粘贴凭证",
            width=96,
            height=30,
            corner_radius=8,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.paste_credentials_manual,
        ).pack(side="right", padx=(12, 0))

    def _build_list(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=3, column=0, sticky="nsew", padx=20, pady=8)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            wrap,
            text="已添加公众号",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.list_frame = ctk.CTkScrollableFrame(
            wrap,
            fg_color=COLORS["bg"],
            corner_radius=12,
        )
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

    def _build_footer(self) -> None:
        foot = ctk.CTkLabel(
            self,
            text="凭证仅保存在本机 certificate/data · 请勿提交真实凭证 · 可用 build.ps1 打包为 exe",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
        )
        foot.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 12))

    def install_ca(self) -> None:
        ok, msg = install_ca_windows(self.root_dir)
        self.proxy_lbl.configure(text=msg, text_color=COLORS["ok"] if ok else COLORS["danger"])
        self.set_status(msg, ok=ok)

    def reveal_ca_file(self) -> None:
        ok, msg = open_p12_in_explorer(self.root_dir)
        self.set_status(msg, ok=ok)

    def toggle_proxy(self) -> None:
        if self.mitm.running:
            ok, msg = self.mitm.stop(restore_proxy=True)
            self.proxy_btn.configure(text="手动启停代理")
            self.proxy_lbl.configure(text=msg, text_color=COLORS["muted"])
            self.set_status(msg, ok=ok)
            return
        ok, msg = self.mitm.start(set_system_proxy=True)
        if ok:
            self.proxy_btn.configure(text="停止抓包代理")
            tip = (
                f"代理运行中 {PROXY_HOST}:{PROXY_PORT}。"
                "请先「添加并抓包」绑定公众号，再在微信里打开文章；"
                "仅开代理不会入库。"
            )
            self.proxy_lbl.configure(text=tip, text_color=COLORS["ok"])
            self.set_status(tip, ok=True)
        else:
            self.proxy_lbl.configure(text=msg, text_color=COLORS["danger"])
            self.set_status(msg.split("\n")[0], ok=False)

    def _ensure_proxy_for_capture(self) -> bool:
        if self.mitm.running:
            return True
        ok, msg = self.mitm.start(set_system_proxy=True)
        if ok:
            self.proxy_btn.configure(text="停止抓包代理")
            self.proxy_lbl.configure(
                text=f"抓包代理已自动启动 {PROXY_HOST}:{PROXY_PORT}",
                text_color=COLORS["ok"],
            )
        else:
            self.proxy_lbl.configure(text=msg, text_color=COLORS["danger"])
            self.set_status(msg, ok=False)
        return ok

    def _capture_target_id(self) -> str | None:
        if self._pending_capture_id:
            return self._pending_capture_id
        for row in self.store.list_accounts():
            if row.get("status") == "awaiting":
                return str(row["id"])
        return None

    def set_status(self, text: str, *, ok: bool | None = None) -> None:
        color = COLORS["muted"]
        if ok is True:
            color = COLORS["ok"]
        elif ok is False:
            color = COLORS["danger"]
        self.status_lbl.configure(text=text, text_color=color)

    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception as exc:
            self.set_status(f"无法打开浏览器: {exc}", ok=False)

    def add_account(self) -> None:
        name = self.name_entry.get().strip()
        url = self.url_entry.get().strip()
        if not url or "mp.weixin.qq.com" not in url:
            self.set_status("请填写有效的公众号文章链接（mp.weixin.qq.com）", ok=False)
            return
        if not self._ensure_proxy_for_capture():
            return
        row = self.store.add_pending(name=name or "未命名公众号", article_url=url)
        self._pending_capture_id = row["id"]
        self.watcher.enable()
        self.name_entry.delete(0, "end")
        self.url_entry.delete(0, "end")
        hint_biz = extract_credentials_from_url(url).get("__biz") or ""
        if self._try_apply_existing_inbox(expected_biz=hint_biz):
            return
        # Fresh wait: drop stale inbox from earlier proxy-only browsing
        self.mitm.clear_inbox()
        self.set_status(
            "已添加并开始抓包。请现在用微信桌面打开该公众号任意一篇文章，等待自动入库。",
            ok=True,
        )

    def renew_account(self, account_id: str) -> None:
        row = self.store.get(account_id)
        if not row:
            return
        if not self._ensure_proxy_for_capture():
            return
        self.store.set_awaiting(account_id)
        self._pending_capture_id = account_id
        self.watcher.enable()
        hint_biz = (
            str(row.get("biz") or "")
            or extract_credentials_from_url(str(row.get("article_url") or "")).get("__biz")
            or ""
        )
        if self._try_apply_existing_inbox(expected_biz=hint_biz):
            return
        self.mitm.clear_inbox()
        self.set_status(
            "续约中：请在微信桌面再打开该公众号任意一篇文章，等待自动捕获。",
            ok=True,
        )

    def _try_apply_existing_inbox(self, *, expected_biz: str = "") -> bool:
        """If proxy was started early and already captured, bind inbox after add/renew.

        Only reuse when we can match ``__biz`` (short links without __biz always
        wait for a fresh WeChat open to avoid binding the wrong account).
        """
        if not expected_biz:
            return False
        self.mitm.reset_inbox_cursor()
        cred = self.mitm.read_new_credentials(consume=False)
        if not cred:
            return False
        if cred.get("__biz") != expected_biz:
            return False
        ok = self._apply_credentials(cred)
        if ok:
            self.mitm.ack_inbox()
        return ok

    def open_article(self, account_id: str) -> None:
        row = self.store.get(account_id)
        if not row:
            return
        url = row.get("article_url") or ""
        if url:
            self._open_url(url)

    def delete_account(self, account_id: str) -> None:
        if self._pending_capture_id == account_id:
            self._pending_capture_id = None
            self.watcher.disable()
        self.store.delete(account_id)
        self.set_status("已删除公众号", ok=True)

    def copy_credentials(self, account_id: str) -> None:
        if not self.store.is_active(account_id):
            self.set_status("凭证已过期，请先续约", ok=False)
            return
        row = self.store.get(account_id)
        if not row:
            return
        cred = row.get("credentials") or {}
        try:
            pyperclip.copy(credentials_to_json(cred))
            self.set_status(f"已复制「{row.get('name')}」凭证 JSON", ok=True)
        except Exception as exc:
            self.set_status(f"复制失败: {exc}", ok=False)

    def paste_credentials_manual(self) -> None:
        try:
            text = pyperclip.paste() or ""
        except Exception:
            text = ""
        cred = try_parse_credentials(text)
        if not cred:
            self.set_status(
                "粘贴失败：剪贴板里没有凭证。请用「添加并抓包」后在微信打开文章自动入库；"
                "「粘贴凭证」仅用于已复制的含 __biz/uin/key 的链接或 JSON。",
                ok=False,
            )
            return
        if self._apply_credentials(cred):
            self.mitm.ack_inbox()

    def _on_clipboard_credentials(self, cred: dict[str, str]) -> None:
        # marshal to UI thread
        self.after(0, lambda: self._apply_credentials(cred))

    def _apply_credentials(self, cred: dict[str, str]) -> bool:
        target = self._capture_target_id()
        if not target:
            self.set_status(
                "已截获凭证，但还没有待绑定的公众号。请填写名称与链接并点「添加并抓包」。",
                ok=False,
            )
            return False
        row = self.store.apply_credentials(target, cred)
        self._pending_capture_id = None
        self.watcher.disable()
        name = (row or {}).get("name") or ""
        self.set_status(f"「{name}」凭证已更新，有效期 {TTL_MINUTES} 分钟", ok=True)
        return True

    def _schedule_rebuild(self) -> None:
        if self._rebuild_job:
            try:
                self.after_cancel(self._rebuild_job)
            except Exception:
                pass
        self._rebuild_job = self.after(50, self._rebuild_list)

    def _rebuild_list(self) -> None:
        self._rebuild_job = None
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._cards.clear()
        rows = self.store.list_accounts()
        if not rows:
            empty = ctk.CTkLabel(
                self.list_frame,
                text="还没有公众号。在上方填写名称与文章链接后点击「添加并抓包」。",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            )
            empty.grid(row=0, column=0, pady=40)
            return
        for i, row in enumerate(rows):
            card = AccountCard(self.list_frame, self, row)
            card.grid(row=i, column=0, sticky="ew", pady=(0, 10))
            self._cards[str(row["id"])] = card

    def _tick(self) -> None:
        self.store.mark_expired_if_needed()
        # MITM inbox: peek first — only consume after successful bind
        cred = self.mitm.read_new_credentials(consume=False)
        if cred:
            if self._capture_target_id():
                if self._apply_credentials(cred):
                    self.mitm.ack_inbox()
            else:
                # Keep inbox for later 「添加并抓包」; avoid silent drop
                pass
        rows = {r["id"]: r for r in self.store.list_accounts()}
        for aid, card in list(self._cards.items()):
            if aid in rows:
                card.refresh(rows[aid])
        # keep proxy button label in sync
        if self.mitm.running:
            self.proxy_btn.configure(text="停止抓包代理")
        else:
            self.proxy_btn.configure(text="手动启停代理")
        self.after(1000, self._tick)

    def _on_close(self) -> None:
        self.watcher.stop()
        try:
            self.mitm.stop(restore_proxy=True)
        except Exception:
            pass
        self.destroy()


def run_app(root_dir: Path) -> None:
    app = CertificateApp(root_dir)
    app.mainloop()
