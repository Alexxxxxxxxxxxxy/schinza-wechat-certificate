"""CustomTkinter desktop UI for Schinza certificate helper."""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pyperclip
from PIL import Image

from app.article_reader import (
    ARTICLE_EXPORT_FORMATS,
    ARTICLE_EXPORT_LABELS,
    batch_export_articles,
    extension_for_article_format,
    fetch_and_parse_article,
    format_key_for_article_label,
    write_article_export,
)
from app.ca_setup import PROXY_HOST, PROXY_PORT, install_ca_windows, open_p12_in_explorer
from app.capture_target import expected_biz, resolve_capture_target
from app.batch_import import BatchRow, parse_batch_import
from app.clipboard_watch import ClipboardWatcher
from app.credentials import (
    credentials_to_json,
    extract_credentials_from_url,
    normalize_credentials,
    try_parse_credentials,
)
from app.history_account_select import pick_label_for_account_id, resolve_account_id
from app.history_client import describe_exception, fetch_history_days
from app.history_export import (
    FORMAT_LABELS,
    default_export_filename,
    extension_for_label,
    format_key_for_label,
    render_export,
    write_export,
)
from app.history_ranges import (
    ALL_LABEL,
    CUSTOM_DAYS_DEFAULT,
    CUSTOM_LABEL,
    DEFAULT_HISTORY_DAYS,
    HISTORY_RANGE_LABELS,
    MAX_CUSTOM_DAYS,
    days_for_label,
    label_for_days,
    range_text,
)
from app.mitm_capture import MitmCaptureService
from app.sightings import SightingsStore, default_sightings_path
from app.store import TTL_MINUTES, AccountStore
from app.updater import (
    RELEASE_URL,
    check_update_async,
    is_newer_than,
)
from app.sync_server import (
    BATCH_LIMIT,
    build_account_payload,
    chunk_accounts,
    parse_school_accounts_csv,
    upload_credentials_batch,
)

# ui-ux-pro-max: exaggerated minimal dark utility — slate + run green
COLORS = {
    "bg": "#0F172A",
    "panel": "#1E293B",
    "card": "#272F42",
    "sidebar": "#111827",
    "border": "#475569",
    "text": "#F8FAFC",
    "muted": "#94A3B8",
    "accent": "#22C55E",
    "accent_hover": "#4ADE80",
    "warn": "#e0a35c",
    "danger": "#EF4444",
    "ok": "#4ADE80",
    "nav_idle": "#1E293B",
}


def _matches_name_filter(name: str, query: str) -> bool:
    """Case-insensitive substring match on 公众号名称 (empty query matches all)."""
    q = (query or "").strip().lower()
    if not q:
        return True
    return q in (name or "").lower()


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
        self.copy_btn.pack(side="left", padx=(0, 14))

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
        self.renew_btn.pack(side="left", padx=(0, 14))

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
        self.open_btn.pack(side="left", padx=(0, 14))

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

        # 续约始终可点：未过期也可主动刷新；等待中可再次点开文章重试
        self.renew_btn.configure(state="normal")

        if status == "active" and remain > 0:
            self.timer_lbl.configure(text=_fmt_remain(remain), text_color=COLORS["ok"])
            self.meta_lbl.configure(
                text=f"有效 · __biz={biz}\n点「续约」后请在微信内刷新该号文章\n{url}"
            )
            self.copy_btn.configure(state="normal")
        elif status == "awaiting":
            self.timer_lbl.configure(text="等待凭证", text_color=COLORS["warn"])
            self.meta_lbl.configure(
                text="续约/抓包中 · 请在微信内刷新该公众号文章\n" + url
            )
            self.copy_btn.configure(state="disabled")
        else:
            self.timer_lbl.configure(text="已过期", text_color=COLORS["danger"])
            self.meta_lbl.configure(
                text=f"已过期 · 点「续约」后在微信内刷新文章重新抓取 · __biz={biz}\n{url}"
            )
            self.copy_btn.configure(state="disabled")


class CertificateApp(ctk.CTk):
    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir = root_dir
        self.store = AccountStore(root_dir / "data" / "accounts.json")
        self.sightings = SightingsStore(default_sightings_path(root_dir))
        self._pending_capture_id: str | None = None
        self._bulk_renew_remaining: set[str] = set()
        self._bulk_renew_total: int = 0
        self._bulk_renew_started_at: float = 0.0
        self._name_filter = ""
        self._bulk_no_capture_hint_shown = False
        self._cards: dict[str, AccountCard] = {}
        self._rebuild_job: str | None = None
        self._tab = "credentials"
        self._history_days: int | None = DEFAULT_HISTORY_DAYS
        self._history_custom_days: int | None = None
        self._history_articles: list[dict[str, Any]] = []
        self._history_account_name: str = ""
        self._history_cred: dict[str, Any] = {}
        self._history_fetching = False
        self._history_cancel = False
        self._article_exporting = False
        self._batch_exporting = False
        self._history_selected: set[str] = set()
        self._account_options: list[tuple[str, str]] = []  # (label, id)
        self._history_account_id: str | None = None
        self._nav_btns: dict[str, ctk.CTkButton] = {}
        self._updating = False
        self._sync_rows: list[dict[str, Any]] = []
        self._sync_config_path = self.root_dir / "data" / "sync_config.json"
        self._sync_accounts_path = self.root_dir / "data" / "school_accounts.json"
        self._sync_log_seq = 0
        self._sync_uploading = False
        self._sync_paused_proxy = False
        self._sync_ui_queue: queue.Queue[tuple[str, str | None] | tuple[None, None]] = (
            queue.Queue()
        )

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Schinza")
        self.geometry("1080x880")
        self.minsize(960, 760)
        self.configure(fg_color=COLORS["bg"])
        self._apply_window_icon()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.mitm = MitmCaptureService(root_dir)

        self._build_header()

        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.main.grid_columnconfigure(1, weight=1)
        self.main.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        self.body = ctk.CTkFrame(self.main, fg_color="transparent")
        self.body.grid(row=0, column=1, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        self.cred_view = ctk.CTkFrame(self.body, fg_color="transparent")
        self.cred_view.grid(row=0, column=0, sticky="nsew")
        self.cred_view.grid_columnconfigure(0, weight=1)
        self.cred_view.grid_rowconfigure(2, weight=1)

        self.hist_view = ctk.CTkFrame(self.body, fg_color="transparent")
        self.hist_view.grid_columnconfigure(0, weight=1)
        self.hist_view.grid_rowconfigure(1, weight=1)

        self._build_mitm_panel()
        self._build_add_form()
        self._build_list()
        self._build_history_panel()
        self._build_sync_panel()
        self._build_footer()

        self.watcher = ClipboardWatcher(self._on_clipboard_credentials)
        self.watcher.start()

        self.store.on_change(self._schedule_rebuild)
        self._rebuild_list()
        self._show_tab("credentials")
        self.after(500, self._tick)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=0, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="w", padx=20, pady=12)

        icon_path = self._resolve_asset("logo-128.png") or self._resolve_asset("logo.png")
        if icon_path is not None:
            try:
                logo_img = Image.open(icon_path)
                self._header_logo = ctk.CTkImage(
                    light_image=logo_img,
                    dark_image=logo_img,
                    size=(32, 32),
                )
                ctk.CTkLabel(title_row, image=self._header_logo, text="").pack(
                    side="left", padx=(0, 10)
                )
            except Exception:
                pass

        ctk.CTkLabel(
            title_row,
            text="Schinza",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=20, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=f"凭证 {TTL_MINUTES} 分钟 · 历史文章 · HTML / MD / TXT / JSON / Word",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=20)

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(
            self.main,
            fg_color=COLORS["sidebar"],
            corner_radius=0,
            width=188,
            border_width=0,
        )
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            side,
            text="栏目",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            text_color=COLORS["muted"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(20, 8))

        for i, (key, label) in enumerate(
            (("credentials", "凭证管理"), ("history", "历史文章"), ("sync", "同步服务器"))
        ):
            btn = ctk.CTkButton(
                side,
                text=label,
                height=40,
                corner_radius=10,
                fg_color=COLORS["nav_idle"],
                hover_color=COLORS["border"],
                text_color=COLORS["text"],
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold"),
                anchor="w",
                command=lambda k=key: self._show_tab(k),
            )
            btn.grid(row=i + 1, column=0, sticky="ew", padx=12, pady=4)
            self._nav_btns[key] = btn

        self.check_update_btn = ctk.CTkButton(
            side,
            text="检查更新",
            height=36,
            corner_radius=10,
            fg_color=COLORS["nav_idle"],
            hover_color=COLORS["border"],
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            anchor="w",
            command=self.manual_check_update,
        )
        self.check_update_btn.grid(
            row=4, column=0, sticky="ew", padx=12, pady=(4, 12)
        )

        side.grid_rowconfigure(5, weight=1)

    def _resolve_asset(self, name: str) -> Path | None:
        import sys

        candidates = [
            self.root_dir / "assets" / name,
            Path(getattr(sys, "_MEIPASS", self.root_dir)) / "assets" / name,
            Path(__file__).resolve().parents[1] / "assets" / name,
        ]
        for p in candidates:
            if p.is_file():
                return p
        return None

    def _apply_window_icon(self) -> None:
        ico = self._resolve_asset("schinza.ico")
        if ico is None:
            return
        try:
            self.iconbitmap(default=str(ico))
        except Exception:
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass
        # Re-apply after window maps (Windows sometimes resets default CTk icon)
        self.after(200, lambda: self._apply_window_icon_once(ico))

    def _apply_window_icon_once(self, ico: Path) -> None:
        try:
            self.iconbitmap(str(ico))
        except Exception:
            pass

    def _show_tab(self, tab: str) -> None:
        self._tab = tab
        for key, btn in self._nav_btns.items():
            if key == tab:
                btn.configure(
                    fg_color=COLORS["accent"],
                    text_color="#052e16",
                    hover_color=COLORS["accent_hover"],
                )
            else:
                btn.configure(
                    fg_color=COLORS["nav_idle"],
                    text_color=COLORS["text"],
                    hover_color=COLORS["border"],
                )
        if tab == "history":
            self.cred_view.grid_remove()
            self.sync_view.grid_remove()
            self.hist_view.grid(row=0, column=0, sticky="nsew")
            self.refresh_history_account_options()
        elif tab == "sync":
            self.cred_view.grid_remove()
            self.hist_view.grid_remove()
            self.sync_view.grid(row=0, column=0, sticky="nsew")
        else:
            self.hist_view.grid_remove()
            self.sync_view.grid_remove()
            self.cred_view.grid(row=0, column=0, sticky="nsew")

    def _build_mitm_panel(self) -> None:
        panel = ctk.CTkFrame(
            self.cred_view,
            fg_color=COLORS["panel"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        panel.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
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
        btns.grid(row=2, column=0, sticky="w", padx=18, pady=(4, 14))

        ctk.CTkButton(
            btns,
            text="安装 CA 证书",
            width=120,
            height=34,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#052e16",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=self.install_ca,
        ).pack(side="left", padx=(0, 16))

        ctk.CTkButton(
            btns,
            text="打开证书文件",
            width=120,
            height=34,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.reveal_ca_file,
        ).pack(side="left", padx=(0, 16))

        self.proxy_btn = ctk.CTkButton(
            btns,
            text="手动启停代理",
            width=120,
            height=34,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=self.toggle_proxy,
        )
        self.proxy_btn.pack(side="left", padx=(0, 16))

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
            self.cred_view,
            fg_color=COLORS["panel"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        form.grid(row=1, column=0, sticky="ew", padx=20, pady=(8, 8))
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
                "再在微信桌面打开该公众号任意一篇文章。"
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

        ctk.CTkButton(
            paste_row,
            text="批量导入",
            width=96,
            height=30,
            corner_radius=8,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.batch_import_accounts,
        ).pack(side="right", padx=(12, 0))

    def _build_list(self) -> None:
        wrap = ctk.CTkFrame(self.cred_view, fg_color="transparent")
        wrap.grid(row=2, column=0, sticky="nsew", padx=20, pady=8)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            head,
            text="已添加公众号",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            head,
            text="一键续约全部",
            width=120,
            height=32,
            corner_radius=10,
            fg_color=COLORS["warn"],
            hover_color="#ebab6e",
            text_color="#1a1208",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=self.renew_all_accounts,
        ).grid(row=0, column=1, sticky="e")

        self.search_entry = ctk.CTkEntry(
            head,
            placeholder_text="按公众号名称搜索…",
            height=32,
            corner_radius=10,
            border_color=COLORS["border"],
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
        )
        self.search_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.search_entry.bind("<KeyRelease>", lambda _e: self._apply_name_filter())

        self.list_frame = ctk.CTkScrollableFrame(
            wrap,
            fg_color=COLORS["bg"],
            corner_radius=12,
        )
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

    def _build_history_panel(self) -> None:
        panel = ctk.CTkFrame(
            self.hist_view,
            fg_color=COLORS["panel"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        panel.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            panel,
            text="拉取公众号历史文章",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            panel,
            text="选择公众号与时间范围后拉取；支持列表导出与正文导出（HTML / Markdown / TXT / JSON / Word）。",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=720,
        ).grid(row=1, column=0, columnspan=4, sticky="ew", padx=18, pady=(0, 10))

        ctk.CTkLabel(
            panel,
            text="公众号",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
        ).grid(row=2, column=0, sticky="w", padx=(18, 8), pady=6)

        self.hist_account_menu = ctk.CTkOptionMenu(
            panel,
            values=["（暂无有效凭证）"],
            height=36,
            corner_radius=10,
            fg_color=COLORS["card"],
            button_color=COLORS["border"],
            button_hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            dropdown_font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=self._on_hist_account_change,
        )
        self.hist_account_menu.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=6)
        self.hist_account_menu.set("（暂无有效凭证）")

        self.hist_range_menu = ctk.CTkOptionMenu(
            panel,
            values=HISTORY_RANGE_LABELS,
            width=130,
            height=36,
            corner_radius=10,
            fg_color=COLORS["card"],
            button_color=COLORS["border"],
            button_hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            dropdown_font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=self._on_history_range_change,
        )
        self.hist_range_menu.set(self._history_range_label())
        self.hist_range_menu.grid(row=2, column=2, sticky="e", padx=(0, 10), pady=6)

        self.hist_fetch_btn = ctk.CTkButton(
            panel,
            text=self._fetch_btn_label(),
            width=120,
            height=36,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#052e16",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=self.start_history_fetch,
        )
        self.hist_fetch_btn.grid(row=2, column=3, sticky="e", padx=(0, 18), pady=6)

        self.hist_status = ctk.CTkLabel(
            panel,
            text="请选择公众号与时间范围后点击拉取。",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            anchor="w",
            justify="left",
            wraplength=720,
        )
        self.hist_status.grid(row=3, column=0, columnspan=4, sticky="ew", padx=18, pady=(8, 4))

        list_tools = ctk.CTkFrame(panel, fg_color="transparent")
        list_tools.grid(row=4, column=0, columnspan=4, sticky="ew", padx=18, pady=(4, 8))

        ctk.CTkLabel(
            list_tools,
            text="列表导出",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
        ).pack(side="left", padx=(0, 10))

        self.hist_format_menu = ctk.CTkOptionMenu(
            list_tools,
            values=FORMAT_LABELS,
            width=128,
            height=32,
            corner_radius=8,
            fg_color=COLORS["card"],
            button_color=COLORS["border"],
            button_hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            dropdown_font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
        )
        self.hist_format_menu.set(FORMAT_LABELS[0])
        self.hist_format_menu.pack(side="left", padx=(0, 14))

        ctk.CTkButton(
            list_tools,
            text="复制列表",
            width=84,
            height=32,
            corner_radius=8,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.copy_history_formatted,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkButton(
            list_tools,
            text="导出列表",
            width=88,
            height=32,
            corner_radius=8,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#052e16",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12, weight="bold"),
            command=self.export_history_file,
        ).pack(side="left", padx=(0, 20))

        ctk.CTkButton(
            list_tools,
            text="补录链接",
            width=88,
            height=32,
            corner_radius=8,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.manual_add_article_url,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkButton(
            list_tools,
            text="刷新",
            width=68,
            height=32,
            corner_radius=8,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.refresh_history_account_options,
        ).pack(side="left")

        batch_tools = ctk.CTkFrame(panel, fg_color="transparent")
        batch_tools.grid(row=5, column=0, columnspan=4, sticky="ew", padx=18, pady=(0, 16))

        ctk.CTkLabel(
            batch_tools,
            text="正文导出",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
        ).pack(side="left", padx=(0, 10))

        self.article_fmt_menu = ctk.CTkOptionMenu(
            batch_tools,
            values=ARTICLE_EXPORT_LABELS,
            width=110,
            height=32,
            corner_radius=8,
            fg_color=COLORS["card"],
            button_color=COLORS["border"],
            button_hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            dropdown_font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
        )
        self.article_fmt_menu.set("Markdown")
        self.article_fmt_menu.pack(side="left", padx=(0, 14))

        ctk.CTkButton(
            batch_tools,
            text="全选",
            width=64,
            height=32,
            corner_radius=8,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.select_all_history,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkButton(
            batch_tools,
            text="取消选择",
            width=84,
            height=32,
            corner_radius=8,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            command=self.clear_history_selection,
        ).pack(side="left", padx=(0, 14))

        self.batch_export_btn = ctk.CTkButton(
            batch_tools,
            text="批量导出",
            width=96,
            height=32,
            corner_radius=8,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#052e16",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12, weight="bold"),
            command=self.batch_export_selected,
        )
        self.batch_export_btn.pack(side="left", padx=(0, 14))

        list_wrap = ctk.CTkFrame(self.hist_view, fg_color="transparent")
        list_wrap.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            list_wrap,
            text="文章列表（勾选后可批量导出正文）",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.hist_list = ctk.CTkScrollableFrame(
            list_wrap,
            fg_color=COLORS["bg"],
            corner_radius=12,
        )
        self.hist_list.grid(row=1, column=0, sticky="nsew")
        self.hist_list.grid_columnconfigure(0, weight=1)

    def _build_sync_panel(self) -> None:
        self.sync_view = ctk.CTkFrame(self.body, fg_color="transparent")
        self.sync_view.grid_columnconfigure(0, weight=1)
        self.sync_view.grid_rowconfigure(1, weight=1)

        panel = ctk.CTkFrame(
            self.sync_view,
            fg_color=COLORS["panel"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        panel.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            panel,
            text="同步服务器",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            panel,
            text="导入 Schinza 公众号列表，将本地有效凭证按名称匹配后分批上传（每批 ≤ 50）。",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=720,
        ).grid(row=1, column=0, columnspan=4, sticky="ew", padx=18, pady=(0, 10))

        ctk.CTkLabel(
            panel,
            text="服务器地址",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
        ).grid(row=2, column=0, sticky="w", padx=(18, 8), pady=6)

        self.sync_base_entry = ctk.CTkEntry(
            panel,
            width=340,
            height=36,
            corner_radius=10,
            fg_color=COLORS["card"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            placeholder_text="https://example.com/schinza",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
        )
        self.sync_base_entry.grid(row=2, column=1, sticky="w", padx=(0, 10), pady=6)

        ctk.CTkButton(
            panel,
            text="导入公众号列表 CSV",
            width=140,
            height=36,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=self._import_school_accounts,
        ).grid(row=2, column=2, sticky="w", padx=(0, 10), pady=6)

        self.sync_upload_btn = ctk.CTkButton(
            panel,
            text="同步上传",
            width=100,
            height=36,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#052e16",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=self._sync_upload,
        )
        self.sync_upload_btn.grid(row=2, column=3, sticky="e", padx=(0, 18), pady=6)

        self.sync_summary_lbl = ctk.CTkLabel(
            panel,
            text="尚未导入公众号列表。",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            anchor="w",
            justify="left",
            wraplength=720,
        )
        self.sync_summary_lbl.grid(row=3, column=0, columnspan=4, sticky="ew", padx=18, pady=(6, 4))

        # 依赖 sync_base_entry 与 sync_summary_lbl 均已创建后才能加载配置/刷新摘要
        self._load_sync_config()

        btns = ctk.CTkFrame(panel, fg_color="transparent")
        btns.grid(row=4, column=0, columnspan=4, sticky="ew", padx=18, pady=(0, 14))

        self.sync_copy_btn = ctk.CTkButton(
            btns,
            text="一键复制全部凭证",
            width=140,
            height=32,
            corner_radius=10,
            fg_color=COLORS["warn"],
            hover_color="#ebab6e",
            text_color="#1a1208",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=self._copy_all_credentials,
        )
        self.sync_copy_btn.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(
            btns,
            text="同步会将匹配到的凭证提交到上方服务器地址，请确认可信后再操作。",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            anchor="w",
        ).pack(side="left")

        log_wrap = ctk.CTkFrame(self.sync_view, fg_color="transparent")
        log_wrap.grid(row=1, column=0, sticky="nsew", padx=20, pady=(4, 16))
        log_wrap.grid_columnconfigure(0, weight=1)
        log_wrap.grid_rowconfigure(0, weight=1)

        self.sync_log = ctk.CTkTextbox(
            log_wrap,
            fg_color=COLORS["bg"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=12,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=COLORS["muted"],
            wrap="none",
        )
        self.sync_log.grid(row=0, column=0, sticky="nsew")
        self.sync_log.configure(state="disabled")

    def _build_footer(self) -> None:
        foot = ctk.CTkLabel(
            self,
            text="Schinza · MIT License · 凭证保存在本机 data/ · 同步上传前请确认目标服务器可信",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
        )
        foot.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 12))

    # ── sync tab ─────────────────────────────────────────────────────

    def _load_sync_config(self) -> None:
        url = ""
        try:
            if self._sync_config_path.exists():
                data = json.loads(self._sync_config_path.read_text(encoding="utf-8"))
                if str(data.get("base_url") or "").strip():
                    url = str(data["base_url"]).strip()
        except Exception:
            pass
        self.sync_base_entry.delete(0, "end")
        self.sync_base_entry.insert(0, url)
        try:
            if self._sync_accounts_path.exists():
                data = json.loads(self._sync_accounts_path.read_text(encoding="utf-8"))
                self._sync_rows = list(data.get("rows") or [])
        except Exception:
            self._sync_rows = []
        self._refresh_sync_summary()

    def _save_sync_config(self) -> None:
        try:
            self._sync_config_path.write_text(
                json.dumps(
                    {"base_url": self.sync_base_entry.get().strip()},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _refresh_sync_summary(self) -> None:
        rows = self._sync_rows
        if not rows:
            self.sync_summary_lbl.configure(
                text="尚未导入公众号列表。",
                text_color=COLORS["muted"],
            )
            return
        total = len(rows)
        premium = sum(1 for r in rows if r.get("source") == "优质")
        school = total - premium
        schools = {r.get("school_name") for r in rows if r.get("school_name")}
        self.sync_summary_lbl.configure(
            text=f"已导入 {total} 条：学校 {school} · 优质 {premium} · 覆盖 {len(schools)} 所学校。",
            text_color=COLORS["ok"],
        )

    def _append_sync_log(self, text: str, color: str | None = None) -> None:
        self.sync_log.configure(state="normal")
        self.sync_log.insert("end", text + "\n")
        if color:
            tag = f"l{self._sync_log_seq}"
            self._sync_log_seq += 1
            self.sync_log.tag_add(tag, f"end-{len(text)+1}c", "end-1c")
            self.sync_log.tag_config(tag, foreground=color)
        self.sync_log.see("end")
        self.sync_log.configure(state="disabled")

    def _import_school_accounts(self) -> None:
        path = filedialog.askopenfilename(
            title="选择公众号列表 CSV",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = Path(path).read_text(encoding="gb18030")
            except UnicodeDecodeError as exc:
                self._append_sync_log(f"导入失败（编码无法识别）：{exc}", COLORS["danger"])
                self.set_status("导入失败（编码无法识别）", ok=False)
                return
        try:
            rows = parse_school_accounts_csv(text)
        except Exception as exc:
            self._append_sync_log(f"导入失败：{exc}", COLORS["danger"])
            self.set_status("导入失败", ok=False)
            return
        if not rows:
            self._append_sync_log("CSV 中没有有效行，已保留上次导入的列表", COLORS["danger"])
            self.set_status("CSV 中没有有效行，已保留上次导入的列表", ok=False)
            return
        self._sync_rows = rows
        try:
            self._sync_accounts_path.write_text(
                json.dumps(
                    {"updated_at": datetime.now().isoformat(timespec="seconds"), "rows": rows},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            self._append_sync_log(f"保存列表失败：{exc}", COLORS["danger"])
        premium = sum(1 for r in rows if r.get("source") == "优质")
        self._refresh_sync_summary()
        self._append_sync_log(f"已导入 {len(rows)} 条公众号（优质 {premium}）：{path}")
        self.set_status(f"已导入 {len(rows)} 条公众号列表", ok=True)

    def _matched_payloads(
        self,
    ) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
        """按 bucket 归类有效账号：matched / no_creds / unmatched / bad_school_id。"""
        self.store.mark_expired_if_needed()
        rows = self._sync_rows
        matched: list[dict[str, Any]] = []
        no_creds: list[str] = []
        unmatched: list[str] = []
        bad_school_id: list[str] = []
        for acc in self.store.list_accounts():
            if acc.get("status") != "active":
                continue
            name = str(acc.get("name") or "").strip()
            label = name or str(acc.get("id"))
            cred = acc.get("credentials") or {}
            if not (cred.get("__biz") and cred.get("uin") and cred.get("key")):
                no_creds.append(label)
                continue
            payload = build_account_payload(acc, rows)
            if payload is not None:
                matched.append(payload)
                continue
            if not name:
                unmatched.append(label)
                continue
            if any((r.get("nickname") or "").strip() == name for r in rows):
                bad_school_id.append(label)
            else:
                unmatched.append(label)
        return matched, no_creds, unmatched, bad_school_id

    def _copy_all_credentials(self) -> None:
        if not self._sync_rows:
            self.set_status("请先导入公众号列表", ok=False)
            return
        matched, no_creds, unmatched, bad_school_id = self._matched_payloads()
        if not matched:
            self._append_sync_log("没有匹配到任何有效凭证账号", COLORS["danger"])
            self.set_status("没有匹配到有效凭证", ok=False)
            return
        try:
            pyperclip.copy(json.dumps({"accounts": matched}, ensure_ascii=False, indent=2))
        except Exception as exc:
            self._append_sync_log(f"复制失败：{exc}", COLORS["danger"])
            self.set_status("复制失败", ok=False)
            return
        if no_creds:
            self._append_sync_log(f"无凭证（跳过）：{', '.join(no_creds)}", COLORS["muted"])
        if unmatched:
            self._append_sync_log(f"未匹配（跳过）：{', '.join(unmatched)}", COLORS["warn"])
        if bad_school_id:
            self._append_sync_log(
                f"无效 school_id（跳过）：{', '.join(bad_school_id)}", COLORS["danger"]
            )
        self._append_sync_log(f"已复制 {len(matched)} 条凭证 JSON 到剪贴板", COLORS["ok"])
        self.set_status(f"已复制 {len(matched)} 条凭证", ok=True)

    def _sync_upload(self) -> None:
        if not self._sync_rows:
            self.set_status("请先导入公众号列表", ok=False)
            return
        matched, no_creds, unmatched, bad_school_id = self._matched_payloads()
        if not matched:
            self._append_sync_log("没有匹配到任何有效凭证账号", COLORS["danger"])
            self.set_status("没有匹配到有效凭证", ok=False)
            return
        base = self.sync_base_entry.get().strip()
        if not base:
            self._append_sync_log("请先填写服务器地址（例如 https://example.com/schinza）", COLORS["danger"])
            self.set_status("缺少服务器地址，已取消同步", ok=False)
            return
        if not base.startswith(("http://", "https://")):
            self._append_sync_log(
                f"服务器地址必须以 http:// 或 https:// 开头，已取消同步：{base}",
                COLORS["danger"],
            )
            self.set_status("服务器地址无效，已取消同步", ok=False)
            return
        self._save_sync_config()
        self.sync_upload_btn.configure(state="disabled")
        self._sync_uploading = True

        # 抓包代理会把上传请求劫持到本地并导致 SSL 校验失败 / 卡住，
        # 同步属于公网直连操作：先暂停代理并还原系统代理，同步完成后再恢复。
        paused = False
        if self.mitm.running:
            ok, msg = self.mitm.stop(restore_proxy=True)
            if ok:
                paused = True
                self._append_sync_log(f"已暂停抓包代理：{msg.splitlines()[0]}", COLORS["warn"])
            else:
                self._append_sync_log(f"暂停代理失败（继续同步）：{msg.splitlines()[0]}", COLORS["warn"])
        self._sync_paused_proxy = paused

        self.set_status(f"开始同步 {len(matched)} 条凭证…", ok=True)
        self._append_sync_log(f"匹配 {len(matched)} 条，未匹配 {len(unmatched)} 条，开始上传")
        if no_creds:
            self._append_sync_log(f"无凭证（跳过）：{', '.join(no_creds)}", COLORS["muted"])
        if unmatched:
            self._append_sync_log(f"未匹配（跳过）：{', '.join(unmatched)}", COLORS["warn"])
        if bad_school_id:
            self._append_sync_log(
                f"无效 school_id（跳过）：{', '.join(bad_school_id)}", COLORS["danger"]
            )

        q = self._sync_ui_queue
        q.put(("__start__", None))

        def worker() -> None:
            batches = chunk_accounts(matched, size=BATCH_LIMIT)
            accepted_total = 0
            failed_total = 0
            try:
                for idx, batch in enumerate(batches, start=1):
                    q.put(
                        (
                            f"[{idx}/{len(batches)}] 正在上传 {len(batch)} 条"
                            f"（服务端逐条校验，每条约 5-8 秒，请耐心等待）…",
                            COLORS["muted"],
                        )
                    )
                    try:
                        resp = upload_credentials_batch(base, batch)
                        accepted = resp.get("accepted") if isinstance(resp, dict) else None
                        failed = resp.get("failed") if isinstance(resp, dict) else None
                        if isinstance(accepted, list) and isinstance(failed, list):
                            accepted_total += len(accepted)
                            failed_total += len(failed)
                            q.put(
                                (
                                    f"[{idx}/{len(batches)}] {len(batch)} 条："
                                    f"成功 {len(accepted)} · 失败 {len(failed)}",
                                    COLORS["ok"] if not failed else COLORS["danger"],
                                )
                            )
                            for item in failed:
                                q.put((f"    - {item}", COLORS["danger"]))
                        else:
                            failed_total += len(batch)
                            snippet = json.dumps(resp, ensure_ascii=False)[:200]
                            q.put(
                                (
                                    f"[{idx}/{len(batches)}] 响应缺少 accepted/failed 列表，"
                                    f"按失败处理：{snippet}",
                                    COLORS["danger"],
                                )
                            )
                    except Exception as exc:
                        failed_total += len(batch)
                        q.put(f"[{idx}/{len(batches)}] 请求失败：{exc}", COLORS["danger"])
            except Exception as exc:  # pragma: no cover - defensive
                failed_total += len(batches) or 1
                q.put(f"同步任务异常：{exc}", COLORS["danger"])
            all_ok = failed_total == 0
            q.put(
                (
                    f"同步完成：成功 {accepted_total} · 失败 {failed_total}"
                    f"（{len(batches)} 批）",
                    COLORS["ok"] if all_ok else COLORS["danger"],
                )
            )
            q.put(("__finish__", str(all_ok)))

        threading.Thread(target=worker, name="schinza-sync-upload", daemon=True).start()

    def _pump_sync_queue(self) -> None:
        """主线程轮询同步上传消息，实时刷新日志。"""
        if not self._sync_uploading:
            return
        try:
            while True:
                msg, color = self._sync_ui_queue.get_nowait()
                if msg == "__start__":
                    continue
                if msg == "__finish__":
                    self._sync_uploading = False
                    self.sync_upload_btn.configure(state="normal")
                    # 同步期间暂停了抓包代理，完成后恢复
                    if self._sync_paused_proxy:
                        self._sync_paused_proxy = False
                        ok, rmsg = self.mitm.start(set_system_proxy=True)
                        if ok:
                            self._append_sync_log(
                                f"已恢复抓包代理：{rmsg.splitlines()[0]}", COLORS["ok"]
                            )
                        else:
                            self._append_sync_log(
                                f"恢复抓包代理失败（可在凭证页手动开启）：{rmsg.splitlines()[0]}",
                                COLORS["danger"],
                            )
                    self.set_status("同步完成", ok=(color == "True"))
                    continue
                self._append_sync_log(msg, color)
        except queue.Empty:
            pass

    # ── credentials tab actions ───────────────────────────────────────

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

    def manual_check_update(self) -> None:
        if self._updating:
            self.set_status("正在检查更新，请稍候…", ok=True)
            return
        self._updating = True
        self.check_update_btn.configure(state="disabled", text="检查中…")
        self.set_status("正在检查更新…", ok=True)
        check_update_async(
            on_result=lambda newer, msg, info: self.after(
                0, lambda: self._on_update_result(newer, msg, info)
            ),
        )

    def _on_update_result(
        self,
        newer: bool,
        msg: str,
        info,
    ) -> None:
        self._updating = False
        if hasattr(self, "check_update_btn"):
            self.check_update_btn.configure(state="normal", text="检查更新")
        if not info:
            self.set_status(msg, ok=False)
            self._show_update_dialog("检查更新", "无法检查更新", msg, ok=False)
            return
        if newer:
            self.set_status(f"{msg}：{info.body[:60]}", ok=True)
            self._show_update_dialog(
                "发现新版本",
                f"发现新版本 {info.version}",
                (info.body or "有可用更新。") + "\n\n是否前往 GitHub 下载？",
                ok=True,
                action_label="前往下载",
                on_action=lambda: self._open_url(info.release_url or RELEASE_URL),
            )
        else:
            self.set_status(msg, ok=True)
            self._show_update_dialog(
                "检查更新",
                "已是最新版",
                f"当前已是最新版本（{msg.split('（')[-1].rstrip('）')}）。",
                ok=True,
            )

    def _show_update_dialog(
        self,
        title: str,
        headline: str,
        body: str,
        *,
        ok: bool,
        action_label: str = "确定",
        on_action: Callable[[], None] | None = None,
    ) -> None:
        """Themed modal for检查更新 — matches app COLORS (like 补录链接)."""
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.configure(fg_color=COLORS["bg"])
        dlg.geometry("480x300")
        dlg.minsize(440, 260)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        try:
            self.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - 480) // 2
            y = self.winfo_rooty() + (self.winfo_height() - 300) // 2
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        card = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=headline,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=16, weight="bold"),
            text_color=COLORS["ok"] if ok else COLORS["danger"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))

        ctk.CTkLabel(
            card,
            text=body,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=420,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="e", padx=18, pady=(8, 16))

        def close() -> None:
            dlg.grab_release()
            dlg.destroy()

        if on_action is not None:
            ctk.CTkButton(
                btns,
                text=action_label,
                width=96,
                height=34,
                corner_radius=10,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                text_color="#0b1412",
                font=ctk.CTkFont(
                    family="Microsoft YaHei UI", size=13, weight="bold"
                ),
                command=lambda: (on_action(), close()),
            ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btns,
            text="关闭",
            width=72,
            height=34,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=close,
        ).pack(side="right")

    def set_hist_status(self, text: str, *, ok: bool | None = None) -> None:
        color = COLORS["muted"]
        if ok is True:
            color = COLORS["ok"]
        elif ok is False:
            color = COLORS["danger"]
        self.hist_status.configure(text=text, text_color=color)

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
        self.mitm.clear_inbox()
        self.set_status(
            "已添加并开始抓包。请现在用微信桌面打开该公众号任意一篇文章，等待自动入库。",
            ok=True,
        )

    def batch_import_accounts(self) -> None:
        """批量导入 CSV/TXT（公众号,文章链接），逐个添加并抓包。"""
        path = filedialog.askopenfilename(
            title="选择批量导入文件（CSV/TXT）",
            filetypes=[
                ("CSV / TXT", "*.csv;*.txt"),
                ("CSV 文件", "*.csv"),
                ("TXT 文件", "*.txt"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = Path(path).read_text(encoding="gb18030")
            except UnicodeDecodeError as exc:
                self.set_status(f"批量导入失败（编码无法识别）：{exc}", ok=False)
                return
        rows, errors = parse_batch_import(text)
        if not rows:
            summary = "；".join(errors[:8]) + ("…" if len(errors) > 8 else "")
            self.set_status(f"批量导入失败：没有有效行（{summary}）", ok=False)
            return

        existing_urls = {
            str(r.get("article_url") or "").strip()
            for r in self.store.list_accounts()
            if str(r.get("article_url") or "").strip()
        }
        dup_lines: list[int] = []
        to_add: list[BatchRow] = []
        for row in rows:
            if row.link in existing_urls:
                dup_lines.append(row.line)
                continue
            to_add.append(row)
            existing_urls.add(row.link)
        if not to_add:
            self.set_status("批量导入失败：所有行都与已有公众号重复", ok=False)
            return

        if not self._ensure_proxy_for_capture():
            return
        for row in to_add:
            self.store.add_pending(name=row.name, article_url=row.link)
        self._pending_capture_id = None
        self.watcher.enable()
        self.mitm.clear_inbox()
        skipped = len(errors) + len(dup_lines)
        base = (
            f"已批量添加 {len(to_add)} 个公众号并开始抓包。"
            "请依次在微信桌面打开各公众号任意一篇文章，等待自动入库。"
        )
        if skipped:
            base += f"（跳过 {skipped} 行：无效/重复）"
        self.set_status(base, ok=True)

    def _clear_bulk_renew(self) -> None:
        self._bulk_renew_remaining = set()
        self._bulk_renew_total = 0
        self._bulk_renew_started_at = 0.0
        self._bulk_no_capture_hint_shown = False

    def _bulk_renew_active(self) -> bool:
        return bool(self._bulk_renew_remaining)

    def renew_account(self, account_id: str) -> None:
        row = self.store.get(account_id)
        if not row:
            return
        if not expected_biz(row) and not str(row.get("article_url") or "").strip():
            self.set_status("该公众号缺少 __biz / 文章链接，无法续约", ok=False)
            return
        if not self._ensure_proxy_for_capture():
            return

        self._clear_bulk_renew()
        # 续约必须重新抓包；不弹系统浏览器，请在微信内刷新已开文章
        self.mitm.reset_capture_state()
        self.store.set_awaiting(account_id)
        self._pending_capture_id = account_id
        self.watcher.enable()

        name = str(row.get("name") or "")
        self.set_status(
            f"「{name}」续约中：请在微信里打开/刷新该公众号文章"
            "（或滚动其历史消息页）。若刷新无反应：先重启微信再打开文章。"
            "抓包明细见 data/capture_debug.log",
            ok=True,
        )

    def renew_all_accounts(self) -> None:
        rows = [
            r
            for r in self.store.list_accounts()
            if expected_biz(r) or str(r.get("article_url") or "").strip()
        ]
        if not rows:
            self.set_status("没有可续约的公众号", ok=False)
            return
        if not self._ensure_proxy_for_capture():
            return

        self.mitm.reset_capture_state()
        self._pending_capture_id = None
        self._bulk_renew_remaining = {str(r["id"]) for r in rows}
        self._bulk_renew_total = len(self._bulk_renew_remaining)
        self._bulk_renew_started_at = time.time()
        self._bulk_no_capture_hint_shown = False
        for aid in self._bulk_renew_remaining:
            self.store.set_awaiting(aid)
        self.watcher.enable()
        self.set_status(
            f"批量续约中（0/{self._bulk_renew_total}）："
            "请在微信内依次打开/刷新各公众号文章（或滚动其历史消息页）。"
            "若刷新无反应：先重启微信（让代理生效）再打开文章。"
            "抓包明细见 data/capture_debug.log",
            ok=True,
        )

    def _try_apply_existing_inbox(self, *, expected_biz: str = "") -> bool:
        if not expected_biz:
            return False
        self.mitm.reset_inbox_cursor()
        creds = self.mitm.read_new_credentials(consume=False)
        for cred in creds:
            if cred.get("__biz") != expected_biz:
                continue
            ok = self._apply_credentials(cred)
            if ok:
                self.mitm.ack_inbox()
                return True
        return False

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
            if not self._bulk_renew_active():
                self.watcher.disable()
        self._bulk_renew_remaining.discard(str(account_id))
        self.store.delete(account_id)
        self.set_status("已删除公众号", ok=True)
        self.refresh_history_account_options()

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
        self.after(0, lambda: self._apply_credentials(cred))

    def _apply_credentials(self, cred: dict[str, str]) -> bool:
        cred = normalize_credentials(cred)
        accounts = self.store.list_accounts()
        bulk = self._bulk_renew_active()
        # Bulk mode: do not pin pending to first awaiting — route purely by __biz
        pending_id = None if bulk else self._capture_target_id()
        result = resolve_capture_target(
            accounts=accounts,
            pending_id=pending_id,
            cred_biz=str(cred.get("__biz") or ""),
        )

        if result.kind == "unknown":
            self.mitm.reset_capture_state()
            if bulk:
                self.watcher.enable()
                left = len(self._bulk_renew_remaining)
                self.set_status(
                    f"已截获流量但 __biz 未匹配到列表中的公众号"
                    f"（可能刷新错了公众号或该号缺少 __biz）；"
                    f"批量续约还剩 {left} 个，请刷新待续约公众号的文章",
                    ok=False,
                )
            elif pending_id:
                self.store.set_awaiting(pending_id)
                self._pending_capture_id = pending_id
                self.watcher.enable()
                tip = result.pending_name or "目标公众号"
                self.set_status(
                    f"已忽略其他公众号流量，请刷新「{tip}」的文章",
                    ok=False,
                )
            else:
                self.set_status(
                    "已截获凭证，但还没有待绑定的公众号。请填写名称与链接并点「添加并抓包」。",
                    ok=False,
                )
            return False

        target = result.account_id
        if not target:
            return False
        row = self.store.apply_credentials(target, cred)
        name = (row or {}).get("name") or result.target_name

        if bulk:
            self._bulk_renew_remaining.discard(str(target))
            done = self._bulk_renew_total - len(self._bulk_renew_remaining)
            total = self._bulk_renew_total
            if self._bulk_renew_remaining:
                self.watcher.enable()
                self.mitm.reset_capture_state()
                self._bulk_renew_started_at = time.time()
                self._bulk_no_capture_hint_shown = False
                self.set_status(
                    f"批量续约 {done}/{total}：已更新「{name}」，"
                    "请继续刷新其余公众号文章（必须刷新）",
                    ok=True,
                )
            else:
                self._clear_bulk_renew()
                self._pending_capture_id = None
                self.watcher.disable()
                self.set_status(
                    f"批量续约完成：共 {total} 个公众号已更新",
                    ok=True,
                )
            self.refresh_history_account_options()
            return True

        if result.kind == "pending" or (
            pending_id and str(pending_id) == str(target)
        ):
            self._pending_capture_id = None
            self.watcher.disable()
            self.set_status(
                f"「{name}」凭证已更新，有效期 {TTL_MINUTES} 分钟",
                ok=True,
            )
        elif pending_id and str(pending_id) != str(target):
            self.store.set_awaiting(pending_id)
            self._pending_capture_id = pending_id
            self.watcher.enable()
            self.mitm.reset_capture_state()
            self.set_status(
                f"已将「{result.target_name}」续约成功"
                f"（当前等待的是「{result.pending_name}」）；"
                f"若还需续约「{result.pending_name}」，请刷新其文章",
                ok=True,
            )
        else:
            self._pending_capture_id = None
            self.watcher.disable()
            self.set_status(
                f"「{result.target_name}」凭证已更新，有效期 {TTL_MINUTES} 分钟",
                ok=True,
            )

        self.refresh_history_account_options()
        return True

    def _apply_name_filter(self) -> None:
        """按公众号名称过滤凭证列表卡片。"""
        self._name_filter = (self.search_entry.get() or "").strip()
        self._rebuild_list()

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
        rows = [
            r
            for r in self.store.list_accounts()
            if _matches_name_filter(str(r.get("name") or ""), self._name_filter)
        ]
        if not rows:
            empty_text = (
                f"没有匹配「{self._name_filter}」的公众号"
                if self._name_filter
                else "还没有公众号。在上方填写名称与文章链接后点击「添加并抓包」。"
            )
            empty = ctk.CTkLabel(
                self.list_frame,
                text=empty_text,
                text_color=COLORS["muted"],
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            )
            empty.grid(row=0, column=0, pady=40)
            return
        for i, row in enumerate(rows):
            card = AccountCard(self.list_frame, self, row)
            card.grid(row=i, column=0, sticky="ew", pady=(0, 10))
            self._cards[str(row["id"])] = card

    # ── history tab ───────────────────────────────────────────────────

    def refresh_history_account_options(self) -> None:
        active = self.store.list_active_accounts()
        prev_label = self.hist_account_menu.get()
        options: list[tuple[str, str]] = []
        labels: list[str] = []
        for row in active:
            aid = str(row["id"])
            remain = self.store.remaining_seconds(aid)
            label = f"{row.get('name') or '未命名'}（剩余 {_fmt_remain(remain)}）"
            options.append((label, aid))
            labels.append(label)
        self._account_options = options
        if not labels:
            labels = ["（暂无有效凭证）"]
            self._history_account_id = None
            self.hist_account_menu.configure(values=labels)
            self.hist_account_menu.set(labels[0])
            return
        keep_id = resolve_account_id(
            options,
            current_label=prev_label,
            preferred_id=self._history_account_id,
        )
        chosen = pick_label_for_account_id(options, keep_id) or labels[0]
        self._history_account_id = next(
            (aid for lb, aid in options if lb == chosen),
            options[0][1],
        )
        self.hist_account_menu.configure(values=labels)
        self.hist_account_menu.set(chosen)

    def _on_hist_account_change(self, value: str) -> None:
        for lb, aid in self._account_options:
            if lb == value:
                self._history_account_id = aid
                return
        # Countdown may have refreshed between click and callback
        aid = resolve_account_id(
            self._account_options,
            current_label=value,
            preferred_id=self._history_account_id,
        )
        if aid:
            self._history_account_id = aid

    def _selected_history_account_id(self) -> str | None:
        return resolve_account_id(
            self._account_options,
            current_label=self.hist_account_menu.get(),
            preferred_id=self._history_account_id,
        )

    def _fetch_btn_label(self) -> str:
        if self._history_days is None:
            return "拉取全部历史"
        return f"拉取近{self._history_days}天"

    def _history_range_label(self) -> str:
        """当前选择对应的下拉框文案（自定义值显示为「自定义 N 天」）。"""
        days = self._history_days
        if days is None:
            return ALL_LABEL
        if label_for_days(days) == CUSTOM_LABEL:
            return f"自定义 {days} 天"
        return label_for_days(days)

    def _on_history_range_change(self, value: str) -> None:
        if value == CUSTOM_LABEL:
            self._prompt_custom_days()
            return
        self._history_days = days_for_label(value)
        self.hist_range_menu.set(self._history_range_label())
        if not self._history_fetching:
            self.hist_fetch_btn.configure(text=self._fetch_btn_label())

    def _prompt_custom_days(self) -> None:
        """Themed modal for 自定义天数 — matches app COLORS (not system simpledialog)."""
        result: dict[str, int | None] = {"days": None}
        prev = self._history_days

        dlg = ctk.CTkToplevel(self)
        dlg.title("自定义天数")
        dlg.configure(fg_color=COLORS["bg"])
        dlg.geometry("440x250")
        dlg.minsize(420, 230)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        # Center over parent
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - 440) // 2
            y = self.winfo_rooty() + (self.winfo_height() - 250) // 2
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        card = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="自定义拉取天数",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=16, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))

        ctk.CTkLabel(
            card,
            text=f"请输入要拉取的天数（1 - {MAX_CUSTOM_DAYS}），例如 15 表示近 15 天。",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=380,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        entry = ctk.CTkEntry(
            card,
            height=40,
            corner_radius=10,
            border_color=COLORS["border"],
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Consolas", size=14),
        )
        entry.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
        entry.insert(0, str(self._history_custom_days or CUSTOM_DAYS_DEFAULT))
        entry.select_range(0, "end")
        entry.focus_set()

        err_lbl = ctk.CTkLabel(
            card,
            text="",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            text_color=COLORS["danger"],
            anchor="w",
        )
        err_lbl.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 4))

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="e", padx=18, pady=(8, 16))

        def close_cancel() -> None:
            result["days"] = None
            dlg.grab_release()
            dlg.destroy()

        def confirm() -> None:
            raw = (entry.get() or "").strip()
            try:
                n = int(raw)
            except ValueError:
                err_lbl.configure(text="请输入整数天数")
                return
            if not (1 <= n <= MAX_CUSTOM_DAYS):
                err_lbl.configure(text=f"天数需在 1 - {MAX_CUSTOM_DAYS} 之间")
                return
            result["days"] = n
            dlg.grab_release()
            dlg.destroy()

        ctk.CTkButton(
            btns,
            text="取消",
            width=88,
            height=34,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=close_cancel,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btns,
            text="确定",
            width=96,
            height=34,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#052e16",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=confirm,
        ).pack(side="left")

        dlg.protocol("WM_DELETE_WINDOW", close_cancel)
        entry.bind("<Return>", lambda _e: confirm())
        entry.bind("<Escape>", lambda _e: close_cancel())

        self.wait_window(dlg)
        n = result["days"]
        if n is None:
            # 取消：恢复原选择
            self.hist_range_menu.set(self._history_range_label())
            return
        self._history_days = n
        self._history_custom_days = n
        self.hist_range_menu.set(self._history_range_label())
        if not self._history_fetching:
            self.hist_fetch_btn.configure(text=self._fetch_btn_label())

    def cancel_history_fetch(self) -> None:
        """请求取消正在进行的拉取（「全部」模式大翻页时避免看起来卡死）。"""
        self._history_cancel = True
        self.set_hist_status("正在取消拉取…", ok=True)

    def start_history_fetch(self) -> None:
        if self._history_fetching:
            return
        self.refresh_history_account_options()
        account_id = self._selected_history_account_id()
        if not account_id:
            self.set_hist_status("没有可用的有效凭证。请先在「凭证管理」抓取凭证。", ok=False)
            return
        if not self.store.is_active(account_id):
            self.set_hist_status("所选公众号凭证已过期，请先续约。", ok=False)
            self.refresh_history_account_options()
            return
        row = self.store.get(account_id)
        if not row:
            return
        cred = dict(row.get("credentials") or {})
        # Prefer credentials.__biz (source of truth for getmsg)
        if not cred.get("__biz") and row.get("biz"):
            cred["__biz"] = row["biz"]

        # History fetch must NOT go through MITM system proxy
        if self.mitm.running:
            self.set_hist_status(
                "提示：抓包代理运行中时，历史拉取会直连微信（绕过系统代理）。正在拉取…",
                ok=True,
            )
        else:
            self.set_hist_status("正在拉取历史文章…", ok=True)

        self._history_fetching = True
        self._history_cancel = False
        self._history_cred = cred
        self.hist_fetch_btn.configure(
            state="normal", text="取消拉取", command=self.cancel_history_fetch
        )
        name = str(row.get("name") or "")
        biz = str(cred.get("__biz") or row.get("biz") or "").strip()
        self.sightings.load()
        sightings = self.sightings.list_for_biz(biz)

        def worker() -> None:
            def progress(msg: str) -> None:
                self.after(0, lambda m=msg: self.set_hist_status(m, ok=True))

            try:
                result = fetch_history_days(
                    cred,
                    days=self._history_days,
                    max_pages=100,
                    on_progress=progress,
                    sightings=sightings,
                    should_cancel=lambda: self._history_cancel,
                )
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": describe_exception(exc), "articles": []}
            self.after(0, lambda: self._on_history_done(name, result))

        threading.Thread(target=worker, name="schinza-history", daemon=True).start()

    def _on_history_done(self, account_name: str, result: dict[str, Any]) -> None:
        self._history_fetching = False
        self.hist_fetch_btn.configure(
            state="normal", text=self._fetch_btn_label(), command=self.start_history_fetch
        )
        if result.get("cancelled"):
            self.set_hist_status(
                f"已取消拉取（已展示部分结果 {len(list(result.get('articles') or []))} 篇）",
                ok=False,
            )
            return
        articles = list(result.get("articles") or [])
        self._history_articles = articles
        self._history_account_name = account_name
        self._history_selected.clear()
        self._render_history_list()
        if not result.get("ok"):
            self.set_hist_status(
                f"拉取失败：{result.get('error') or '未知错误'}（已展示部分结果 {len(articles)} 篇）"
                if articles
                else f"拉取失败：{result.get('error') or '未知错误'}",
                ok=False,
            )
            return
        pages = result.get("pages") or 0
        warn = str(result.get("warning") or "").strip()
        msg = f"「{account_name}」{range_text(self._history_days)}共 {len(articles)} 篇（请求 {pages} 页）"
        if warn:
            msg = f"{msg} · {warn}"
        self.set_hist_status(msg, ok=True)

    def _render_history_text(self) -> tuple[str, str]:
        """Return (format_label, rendered text)."""
        label = self.hist_format_menu.get()
        key = format_key_for_label(label)
        text = render_export(
            self._history_articles,
            fmt=key,
            account_name=self._history_account_name,
            days=self._history_days,
        )
        return label, text

    def _article_key(self, art: dict[str, Any]) -> str:
        return str(art.get("identity") or art.get("link") or art.get("title") or "")

    def select_all_history(self) -> None:
        self._history_selected = {
            self._article_key(a) for a in self._history_articles if self._article_key(a)
        }
        self._render_history_list()
        self.set_hist_status(f"已全选 {len(self._history_selected)} 篇", ok=True)

    def clear_history_selection(self) -> None:
        self._history_selected.clear()
        self._render_history_list()
        self.set_hist_status("已取消选择", ok=True)

    def _toggle_history_select(self, key: str, checked: bool) -> None:
        if not key:
            return
        if checked:
            self._history_selected.add(key)
        else:
            self._history_selected.discard(key)

    def _render_history_list(self) -> None:
        for child in self.hist_list.winfo_children():
            child.destroy()
        if not self._history_articles:
            ctk.CTkLabel(
                self.hist_list,
                text="暂无文章。选择有效凭证后点击拉取。",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            ).grid(row=0, column=0, pady=40)
            return
        for i, art in enumerate(self._history_articles):
            card = ctk.CTkFrame(
                self.hist_list,
                fg_color=COLORS["card"],
                corner_radius=12,
                border_width=1,
                border_color=COLORS["border"],
            )
            card.grid(row=i, column=0, sticky="ew", pady=(0, 12))
            card.grid_columnconfigure(1, weight=1)

            key = self._article_key(art)
            var = ctk.BooleanVar(value=key in self._history_selected)
            ctk.CTkCheckBox(
                card,
                text="",
                width=28,
                checkbox_width=20,
                checkbox_height=20,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                border_color=COLORS["border"],
                variable=var,
                command=lambda k=key, v=var: self._toggle_history_select(k, bool(v.get())),
            ).grid(row=0, column=0, rowspan=3, sticky="n", padx=(14, 6), pady=14)

            title = art.get("title") or "(无标题)"
            when = art.get("publish_at") or ""
            digest = (art.get("digest") or "")[:80]
            link = art.get("link") or ""
            source = str(art.get("source") or "getmsg")
            source_tag = {
                "getmsg": "",
                "mitm": " · 抓包补全",
                "mitm_getmsg": " · 抓包补全",
                "manual": " · 补录",
                "sighting": " · 补全",
            }.get(source, f" · {source}" if source != "getmsg" else "")

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold"),
                text_color=COLORS["text"],
                anchor="w",
                justify="left",
                wraplength=640,
            ).grid(row=0, column=1, sticky="w", padx=(0, 14), pady=(12, 2))

            meta = when + (f"  ·  {digest}" if digest else "") + source_tag
            ctk.CTkLabel(
                card,
                text=meta or link[:72],
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
                text_color=COLORS["muted"],
                anchor="w",
                justify="left",
                wraplength=640,
            ).grid(row=1, column=1, sticky="w", padx=(0, 14), pady=(0, 8))

            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.grid(row=2, column=1, sticky="e", padx=(0, 14), pady=(0, 14))

            ctk.CTkButton(
                actions,
                text="打开",
                width=60,
                height=30,
                corner_radius=8,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                text_color="#052e16",
                command=lambda u=link: self._open_url(u),
            ).pack(side="left", padx=(0, 12))

            ctk.CTkButton(
                actions,
                text="复制链接",
                width=80,
                height=30,
                corner_radius=8,
                fg_color=COLORS["border"],
                hover_color="#3a4a5e",
                command=lambda u=link: self._copy_text(u, "已复制链接"),
            ).pack(side="left", padx=(0, 12))

            fmt_menu = ctk.CTkOptionMenu(
                actions,
                values=ARTICLE_EXPORT_LABELS,
                width=110,
                height=30,
                corner_radius=8,
                fg_color=COLORS["bg"],
                button_color=COLORS["border"],
                button_hover_color="#3a4a5e",
                text_color=COLORS["text"],
                font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
                dropdown_font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            )
            fmt_menu.set(self.article_fmt_menu.get() if hasattr(self, "article_fmt_menu") else "Markdown")
            fmt_menu.pack(side="left", padx=(0, 12))

            ctk.CTkButton(
                actions,
                text="导出",
                width=68,
                height=30,
                corner_radius=8,
                fg_color=COLORS["border"],
                hover_color="#3a4a5e",
                command=lambda a=art, m=fmt_menu: self.export_article(
                    a, fmt=format_key_for_article_label(m.get())
                ),
            ).pack(side="left")

    def _copy_text(self, text: str, ok_msg: str) -> None:
        try:
            pyperclip.copy(text or "")
            self.set_hist_status(ok_msg, ok=True)
        except Exception as exc:
            self.set_hist_status(f"复制失败: {exc}", ok=False)

    def copy_history_formatted(self) -> None:
        if not self._history_articles:
            self.set_hist_status("没有可复制的文章", ok=False)
            return
        try:
            label, text = self._render_history_text()
            pyperclip.copy(text)
            self.set_hist_status(
                f"已按「{label}」复制 {len(self._history_articles)} 篇到剪贴板",
                ok=True,
            )
        except Exception as exc:
            self.set_hist_status(f"复制失败: {exc}", ok=False)

    def export_history_file(self) -> None:
        if not self._history_articles:
            self.set_hist_status("没有可导出的文章", ok=False)
            return
        label = self.hist_format_menu.get()
        ext = extension_for_label(label)
        default_name = default_export_filename(
            account_name=self._history_account_name,
            days=self._history_days,
            ext=ext,
        )
        initial_dir = str((self.root_dir / "data").resolve())
        Path(initial_dir).mkdir(parents=True, exist_ok=True)
        filetypes = [
            (label, f"*.{ext}"),
            ("所有文件", "*.*"),
        ]
        path_str = filedialog.asksaveasfilename(
            parent=self,
            title="导出文章列表",
            initialdir=initial_dir,
            initialfile=default_name,
            defaultextension=f".{ext}",
            filetypes=filetypes,
        )
        if not path_str:
            return
        try:
            _label, text = self._render_history_text()
            path = write_export(Path(path_str), text)
            self.set_hist_status(
                f"已导出 {_label}（{len(self._history_articles)} 篇）→ {path}",
                ok=True,
            )
        except Exception as exc:
            self.set_hist_status(f"导出失败: {exc}", ok=False)

    def _ask_article_url_dialog(self) -> str | None:
        """Themed modal for补录链接 — matches app COLORS (not system simpledialog)."""
        result: dict[str, str | None] = {"url": None}

        dlg = ctk.CTkToplevel(self)
        dlg.title("补录文章链接")
        dlg.configure(fg_color=COLORS["bg"])
        dlg.geometry("520x260")
        dlg.minsize(480, 240)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        # Center over parent
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - 520) // 2
            y = self.winfo_rooty() + (self.winfo_height() - 260) // 2
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        card = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="补录文章链接",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=16, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))

        ctk.CTkLabel(
            card,
            text="粘贴公众号文章链接，将合并进当前列表。",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=440,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        entry = ctk.CTkEntry(
            card,
            height=40,
            corner_radius=10,
            border_color=COLORS["border"],
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            placeholder_text="https://mp.weixin.qq.com/s/…",
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        entry.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
        entry.focus_set()

        err_lbl = ctk.CTkLabel(
            card,
            text="",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            text_color=COLORS["danger"],
            anchor="w",
        )
        err_lbl.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 4))

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="e", padx=18, pady=(8, 16))

        def close_cancel() -> None:
            result["url"] = None
            dlg.grab_release()
            dlg.destroy()

        def confirm() -> None:
            raw = (entry.get() or "").strip()
            if not raw:
                err_lbl.configure(text="请粘贴文章链接")
                return
            if "mp.weixin.qq.com" not in raw:
                err_lbl.configure(text="请输入微信公众号文章链接（mp.weixin.qq.com）")
                return
            result["url"] = raw
            dlg.grab_release()
            dlg.destroy()

        ctk.CTkButton(
            btns,
            text="取消",
            width=88,
            height=34,
            corner_radius=10,
            fg_color=COLORS["border"],
            hover_color="#3a4a5e",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13),
            command=close_cancel,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btns,
            text="补录",
            width=96,
            height=34,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#052e16",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            command=confirm,
        ).pack(side="left")

        dlg.protocol("WM_DELETE_WINDOW", close_cancel)
        entry.bind("<Return>", lambda _e: confirm())
        entry.bind("<Escape>", lambda _e: close_cancel())

        self.wait_window(dlg)
        return result["url"]

    def manual_add_article_url(self) -> None:
        """补录一篇文章链接并合并进当前列表。"""
        account_id = self._selected_history_account_id()
        row = self.store.get(account_id) if account_id else None
        biz = ""
        if row:
            cred = row.get("credentials") or {}
            biz = str(cred.get("__biz") or row.get("biz") or "").strip()

        url = self._ask_article_url_dialog()
        if not url:
            return

        self.set_hist_status("正在读取补录文章标题…", ok=True)
        cred = dict(self._history_cred or (row.get("credentials") if row else {}) or {})

        def worker() -> None:
            try:
                art = fetch_and_parse_article(url, cred=cred or None)
                sighting = {
                    "title": art.get("title") or "",
                    "link": art.get("link") or url,
                    "publish_ts": int(art.get("publish_ts") or 0),
                    "publish_at": art.get("publish_at") or "",
                    "__biz": biz,
                    "source": "manual",
                    "digest": "",
                }
                self.sightings.upsert(sighting)
                err = ""
            except Exception as exc:  # noqa: BLE001
                # Still save bare URL so merge can keep it
                self.sightings.upsert(
                    {
                        "title": "(补录，待读正文)",
                        "link": url,
                        "__biz": biz,
                        "source": "manual",
                        "publish_ts": 0,
                    }
                )
                art = {"title": "(补录，待读正文)", "link": url}
                err = describe_exception(exc)
            self.after(0, lambda: self._on_manual_add_done(art, err))

        threading.Thread(target=worker, name="schinza-manual-add", daemon=True).start()

    def _on_manual_add_done(self, art: dict[str, Any], err: str) -> None:
        title = art.get("title") or "(无标题)"
        if err:
            self.set_hist_status(
                f"已补录链接（正文暂读失败：{err}）。请再点「{self._fetch_btn_label()}」合并进列表。",
                ok=False,
            )
        else:
            self.set_hist_status(
                f"已补录「{title}」。再点「{self._fetch_btn_label()}」即可合并进列表。",
                ok=True,
            )
        # Soft-merge into current list without full refetch
        link = str(art.get("link") or "")
        if link:
            exists = any(
                (a.get("link") == link)
                or (
                    a.get("identity")
                    and a.get("identity") == art.get("identity")
                )
                for a in self._history_articles
            )
            if not exists:
                row = {
                    "title": art.get("title") or "(无标题)",
                    "link": link,
                    "digest": "",
                    "publish_ts": int(art.get("publish_ts") or 0),
                    "publish_at": art.get("publish_at") or "",
                    "source": "manual",
                    "identity": art.get("identity") or link,
                }
                self._history_articles.insert(0, row)
                self._history_articles.sort(
                    key=lambda a: int(a.get("publish_ts") or 0), reverse=True
                )
                self._render_history_list()

    def _resolve_article_fmt(self, fmt: str) -> str:
        raw = (fmt or "markdown").strip()
        if raw in ARTICLE_EXPORT_LABELS:
            return format_key_for_article_label(raw)
        key = raw.lower()
        if key in ("md",):
            return "markdown"
        if key in ("text",):
            return "txt"
        if key in ("docx", "doc"):
            return "word"
        if key not in ARTICLE_EXPORT_FORMATS:
            return "markdown"
        return key

    def export_article(self, art: dict[str, Any], *, fmt: str) -> None:
        if self._article_exporting or self._batch_exporting:
            self.set_hist_status("正在导出中，请稍候…", ok=False)
            return
        link = str(art.get("link") or "").strip()
        if not link:
            self.set_hist_status("该条目没有链接，无法导出正文", ok=False)
            return
        fmt_key = self._resolve_article_fmt(fmt)
        title = str(art.get("title") or "article")
        safe = re.sub(r'[\\/:*?"<>|]+', "_", title)[:48] or "article"
        ext = extension_for_article_format(fmt_key)
        label = ARTICLE_EXPORT_FORMATS.get(fmt_key, fmt_key.upper())
        initial_dir = str((self.root_dir / "data" / "exports").resolve())
        Path(initial_dir).mkdir(parents=True, exist_ok=True)
        path_str = filedialog.asksaveasfilename(
            parent=self,
            title=f"导出文章为 {label}",
            initialdir=initial_dir,
            initialfile=f"{safe}.{ext}",
            defaultextension=f".{ext}",
            filetypes=[
                (label, f"*.{ext}"),
                ("所有文件", "*.*"),
            ],
        )
        if not path_str:
            return

        self._article_exporting = True
        self.set_hist_status(f"正在读取正文并导出 {label}…", ok=True)
        cred = dict(self._history_cred or {})

        def worker() -> None:
            try:
                parsed = fetch_and_parse_article(link, cred=cred or None)
                if not parsed.get("publish_at") and art.get("publish_at"):
                    parsed["publish_at"] = art.get("publish_at")
                if not parsed.get("publish_ts") and art.get("publish_ts"):
                    parsed["publish_ts"] = art.get("publish_ts")
                path = write_article_export(Path(path_str), parsed, fmt_key)
                err = ""
            except Exception as exc:  # noqa: BLE001
                path = Path(path_str)
                err = describe_exception(exc)
            self.after(
                0,
                lambda: self._on_article_export_done(path if not err else None, err, ext),
            )

        threading.Thread(target=worker, name="schinza-article-export", daemon=True).start()

    def _on_article_export_done(
        self, path: Path | None, err: str, ext: str
    ) -> None:
        self._article_exporting = False
        if err or path is None:
            self.set_hist_status(f"导出失败：{err or '未知错误'}", ok=False)
            return
        self.set_hist_status(f"已导出 {ext.upper()} → {path}", ok=True)

    def batch_export_selected(self) -> None:
        if self._batch_exporting or self._article_exporting:
            self.set_hist_status("正在导出中，请稍候…", ok=False)
            return
        if not self._history_articles:
            self.set_hist_status("没有可导出的文章，请先拉取历史", ok=False)
            return
        selected = [
            a
            for a in self._history_articles
            if self._article_key(a) in self._history_selected
        ]
        if not selected:
            selected = list(self._history_articles)
            self.set_hist_status(
                f"未勾选文章，将导出全部 {len(selected)} 篇…", ok=True
            )
        fmt_key = self._resolve_article_fmt(self.article_fmt_menu.get())
        label = ARTICLE_EXPORT_FORMATS.get(fmt_key, fmt_key)
        initial_dir = str((self.root_dir / "data" / "exports").resolve())
        Path(initial_dir).mkdir(parents=True, exist_ok=True)
        dir_str = filedialog.askdirectory(
            parent=self,
            title=f"选择批量导出目录（{label} · {len(selected)} 篇）",
            initialdir=initial_dir,
        )
        if not dir_str:
            return

        self._batch_exporting = True
        self.batch_export_btn.configure(state="disabled", text="导出中…")
        self.set_hist_status(f"批量导出 {len(selected)} 篇为 {label}…", ok=True)
        cred = dict(self._history_cred or {})

        def worker() -> None:
            try:
                result = batch_export_articles(
                    selected,
                    out_dir=Path(dir_str),
                    fmt=fmt_key,
                    cred=cred or None,
                    on_progress=lambda m: self.after(
                        0, lambda msg=m: self.set_hist_status(msg, ok=True)
                    ),
                )
                err = ""
            except Exception as exc:  # noqa: BLE001
                result = {"ok": 0, "failed": len(selected), "out_dir": dir_str}
                err = describe_exception(exc)
            self.after(0, lambda: self._on_batch_export_done(result, err, label))

        threading.Thread(target=worker, name="schinza-batch-export", daemon=True).start()

    def _on_batch_export_done(
        self, result: dict[str, Any], err: str, label: str
    ) -> None:
        self._batch_exporting = False
        self.batch_export_btn.configure(state="normal", text="批量导出")
        if err:
            self.set_hist_status(f"批量导出失败：{err}", ok=False)
            return
        ok_n = int(result.get("ok") or 0)
        fail_n = int(result.get("failed") or 0)
        out = result.get("out_dir") or ""
        self.set_hist_status(
            f"批量导出完成（{label}）：成功 {ok_n} · 失败 {fail_n} → {out}",
            ok=fail_n == 0,
        )

    # ── tick / lifecycle ──────────────────────────────────────────────

    def _tick(self) -> None:
        self.store.mark_expired_if_needed()
        self._pump_sync_queue()
        creds = self.mitm.read_new_credentials(consume=False)
        if creds and (self._bulk_renew_active() or self._capture_target_id()):
            applied = False
            for cred in creds:
                if self._apply_credentials(cred):
                    applied = True
            if applied:
                self.mitm.ack_inbox()
        if self._bulk_renew_active() and not self._bulk_no_capture_hint_shown:
            if time.time() - self._bulk_renew_started_at > 20:
                self._bulk_no_capture_hint_shown = True
                self.set_status(
                    "仍未捕获到微信流量：请先重启微信，再重新打开/刷新各公众号文章"
                    "（或滚动其历史消息页）；抓包明细见 data/capture_debug.log",
                    ok=False,
                )
        rows = {r["id"]: r for r in self.store.list_accounts()}
        for aid, card in list(self._cards.items()):
            if aid in rows:
                card.refresh(rows[aid])
        if self.mitm.running:
            self.proxy_btn.configure(text="停止抓包代理")
        else:
            self.proxy_btn.configure(text="手动启停代理")
        if self._tab == "history" and not self._history_fetching:
            # keep countdown labels in dropdown reasonably fresh
            pass
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
