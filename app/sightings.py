"""Persist article URL sightings (MITM browse / getmsg tap / manual 补录).

WeChat ``getmsg`` sometimes omits later same-day pushes. Sightings fill those gaps
when the user opens articles (or history) through the local MITM proxy, or补录链接.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.history_client import _clean_url, _mid_idx_sn, article_identity


def default_sightings_path(root: Path) -> Path:
    return root / "data" / "article_sightings.json"


def _iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _biz_from_link(link: str) -> str:
    try:
        q = parse_qs(urlparse(link).query)
    except Exception:
        return ""
    vals = q.get("__biz") or []
    return unquote(vals[0]) if vals else ""


class SightingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._rows: list[dict[str, Any]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._rows = []
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                rows = data.get("sightings") if isinstance(data, dict) else data
                self._rows = list(rows) if isinstance(rows, list) else []
            except Exception:
                self._rows = []

    def save(self) -> None:
        with self._lock:
            payload = {"sightings": self._rows, "updated_at": _iso_now()}
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def list_for_biz(self, biz: str, *, cutoff_ts: int = 0) -> list[dict[str, Any]]:
        biz = (biz or "").strip()
        with self._lock:
            out = []
            for row in self._rows:
                rb = str(row.get("__biz") or "").strip()
                if biz:
                    if rb != biz:
                        continue
                ts = int(row.get("publish_ts") or 0)
                if cutoff_ts and ts and ts < cutoff_ts:
                    continue
                out.append(deepcopy(row))
            return out

    def upsert(self, sighting: dict[str, Any]) -> dict[str, Any] | None:
        """Insert or refresh a sighting. Returns the stored row, or None if invalid."""
        link = _clean_url(str(sighting.get("link") or ""))
        title = str(sighting.get("title") or "").strip()
        if not link and not title:
            return None
        mid, idx, sn = _mid_idx_sn(link)
        biz = str(sighting.get("__biz") or "").strip() or _biz_from_link(link)
        publish_ts = int(sighting.get("publish_ts") or 0)
        publish_at = str(sighting.get("publish_at") or "")
        if publish_ts and not publish_at:
            publish_at = datetime.fromtimestamp(publish_ts).strftime("%Y-%m-%d %H:%M")
        identity = str(sighting.get("identity") or "") or article_identity(
            link,
            title=title or "(无标题)",
            publish_ts=publish_ts,
        )
        row = {
            "title": title or "(无标题)",
            "link": link,
            "digest": str(sighting.get("digest") or "").strip(),
            "cover": str(sighting.get("cover") or "").strip(),
            "author": str(sighting.get("author") or "").strip(),
            "publish_ts": publish_ts,
            "publish_at": publish_at,
            "mid": mid,
            "idx": idx or "1",
            "sn": sn,
            "identity": identity,
            "__biz": biz,
            "source": str(sighting.get("source") or "manual"),
            "seen_at": _iso_now(),
        }
        with self._lock:
            for i, old in enumerate(self._rows):
                old_id = str(old.get("identity") or "")
                if old_id and old_id == identity:
                    merged = dict(old)
                    for k, v in row.items():
                        if k == "title" and v and v != "(无标题)":
                            merged[k] = v
                        elif k == "publish_ts" and int(v or 0) > int(merged.get(k) or 0):
                            merged[k] = v
                            merged["publish_at"] = row["publish_at"]
                        elif k == "link" and v and (
                            not merged.get(k)
                            or ("mid=" in v and "mid=" not in str(merged.get(k)))
                        ):
                            merged[k] = v
                        elif k not in merged or not merged.get(k):
                            merged[k] = v
                    merged["seen_at"] = row["seen_at"]
                    merged["source"] = row["source"] or merged.get("source")
                    self._rows[i] = merged
                    self.save()
                    return deepcopy(merged)
            self._rows.insert(0, row)
            if len(self._rows) > 5000:
                self._rows = self._rows[:5000]
            self.save()
            return deepcopy(row)
