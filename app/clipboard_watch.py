"""Poll clipboard for WeChat credential URLs / JSON."""

from __future__ import annotations

import threading
import time
from typing import Callable

import pyperclip

from app.credentials import try_parse_credentials


class ClipboardWatcher:
    def __init__(
        self,
        on_credentials: Callable[[dict[str, str]], None],
        *,
        interval: float = 0.8,
    ) -> None:
        self._on_credentials = on_credentials
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last = ""
        self._enabled = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="clipboard-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._enabled = False

    def enable(self) -> None:
        try:
            self._last = pyperclip.paste() or ""
        except Exception:
            self._last = ""
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._enabled:
                try:
                    text = pyperclip.paste() or ""
                except Exception:
                    text = ""
                if text and text != self._last:
                    self._last = text
                    cred = try_parse_credentials(text)
                    if cred:
                        try:
                            self._on_credentials(cred)
                        except Exception:
                            pass
            time.sleep(self._interval)
