"""Persist account rows under certificate/data/accounts.json."""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

TTL_MINUTES = 30


def _now() -> datetime:
    return datetime.now()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


class AccountStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._accounts: list[dict[str, Any]] = []
        self._listeners: list[Callable[[], None]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def _emit(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._accounts = []
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                rows = data.get("accounts") if isinstance(data, dict) else data
                self._accounts = list(rows) if isinstance(rows, list) else []
            except Exception:
                self._accounts = []

    def save(self) -> None:
        with self._lock:
            payload = {"accounts": self._accounts, "updated_at": _iso(_now())}
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._accounts)

    def get(self, account_id: str) -> dict[str, Any] | None:
        with self._lock:
            for row in self._accounts:
                if row.get("id") == account_id:
                    return deepcopy(row)
        return None

    def add_pending(self, *, name: str, article_url: str) -> dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "name": name.strip() or "未命名公众号",
            "article_url": article_url.strip(),
            "credentials": {},
            "expires_at": None,
            "captured_at": None,
            "status": "awaiting",  # awaiting | active | expired
            "created_at": _iso(_now()),
        }
        with self._lock:
            self._accounts.insert(0, row)
            self.save()
        self._emit()
        return deepcopy(row)

    def apply_credentials(self, account_id: str, credentials: dict[str, str]) -> dict[str, Any] | None:
        expires = _now() + timedelta(minutes=TTL_MINUTES)
        with self._lock:
            for row in self._accounts:
                if row.get("id") != account_id:
                    continue
                row["credentials"] = dict(credentials)
                row["expires_at"] = _iso(expires)
                row["captured_at"] = _iso(_now())
                row["status"] = "active"
                if credentials.get("__biz"):
                    row["biz"] = credentials["__biz"]
                self.save()
                out = deepcopy(row)
                break
            else:
                return None
        self._emit()
        return out

    def set_biz(self, account_id: str, biz: str) -> None:
        """给账号写入已知的 __biz（如从文章页自动提取的），便于抓包匹配。"""
        biz = (biz or "").strip()
        if not biz:
            return
        with self._lock:
            for row in self._accounts:
                if row.get("id") == account_id:
                    row["biz"] = biz
                    cred = row.get("credentials") or {}
                    if isinstance(cred, dict):
                        cred["__biz"] = biz
                        row["credentials"] = cred
                    self.save()
                    break
        self._emit()

    def mark_expired_if_needed(self) -> bool:
        changed = False
        now = _now()
        with self._lock:
            for row in self._accounts:
                exp = _parse_iso(row.get("expires_at"))
                if row.get("status") == "active" and (exp is None or exp <= now):
                    row["status"] = "expired"
                    changed = True
            if changed:
                self.save()
        if changed:
            self._emit()
        return changed

    def remaining_seconds(self, account_id: str) -> int:
        row = self.get(account_id)
        if not row:
            return 0
        exp = _parse_iso(row.get("expires_at"))
        if not exp:
            return 0
        return max(0, int((exp - _now()).total_seconds()))

    def is_active(self, account_id: str) -> bool:
        self.mark_expired_if_needed()
        row = self.get(account_id)
        return bool(row and row.get("status") == "active" and self.remaining_seconds(account_id) > 0)

    def list_active_accounts(self) -> list[dict[str, Any]]:
        self.mark_expired_if_needed()
        with self._lock:
            rows = []
            for row in self._accounts:
                if row.get("status") != "active":
                    continue
                exp = _parse_iso(row.get("expires_at"))
                if exp is None or exp <= _now():
                    continue
                cred = row.get("credentials") or {}
                if not (cred.get("__biz") and cred.get("uin") and cred.get("key")):
                    continue
                rows.append(deepcopy(row))
            return rows

    def delete(self, account_id: str) -> None:
        with self._lock:
            self._accounts = [r for r in self._accounts if r.get("id") != account_id]
            self.save()
        self._emit()

    def set_awaiting(self, account_id: str) -> None:
        with self._lock:
            for row in self._accounts:
                if row.get("id") == account_id:
                    row["status"] = "awaiting"
                    self.save()
                    break
        self._emit()
