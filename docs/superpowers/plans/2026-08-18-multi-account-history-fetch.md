# Multi-Account Queued History Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make single-account `getmsg` paging less likely to trip WeChat risk control, and add a queued multi-account history fetch on the existing History tab.

**Architecture:** MITM capture stores a small client fingerprint on each credential. `fetch_history_days` replays that fingerprint and uses slower page pacing. A new `fetch_history_batch` calls it one account at a time. The History tab adds checkboxes and grouped results; single-account fetch stays.

**Tech Stack:** Python 3.11+, `requests`, CustomTkinter, stdlib `unittest` (no new test framework / no pytest dependency).

**Spec:** `docs/superpowers/specs/2026-08-18-multi-account-history-fetch-design.md`

## Global Constraints

- Sequential queue only — never fetch two accounts' `getmsg` at the same time.
- On `unknownerror` / `freq` / 频繁 / 操作频繁 / 风控: stop that account immediately, keep partial articles, do **not** retry that error, continue the next account.
- History requests stay `session.trust_env = False` (bypass system / MITM proxy).
- Do not persist or replay a raw full `Cookie` header; only listed keys.
- Do not change Sync Server upload, batch-import capture, or article-body export pacing.
- Credential TTL stays 30 minutes.
- UI copy is Chinese, matching the current History tab.
- Tests: `python -m unittest discover -s tests -v` from repo root.

## File map

| File | Responsibility |
|---|---|
| `app/credentials.py` | Optional fingerprint keys in normalize / JSON |
| `app/mitm_addon.py` | Extract and save fingerprint with creds |
| `app/mitm_capture.py` | Inbox reader must pass fingerprint keys through |
| `app/history_client.py` | Slower defaults, replay fingerprint, `stopped_reason` |
| `app/history_batch.py` | **Create** — serial orchestrator |
| `app/history_batch_ui.py` | **Create** — selection / label / summary helpers |
| `app/ui.py` | Checkboxes, batch button, group bar |
| `tests/*.py` | **Create** — unittest for the new logic |

`app/errors.py` is unchanged unless a test forces a one-line hint tweak.

---

### Task 1: Credential optional fingerprint keys

**Files:**
- Modify: `app/credentials.py`
- Test: `tests/test_credentials.py` (create)
- Create: `tests/__init__.py` (empty)

**Interfaces:**
- Consumes: existing `normalize_credentials`, `credentials_enough`, `credentials_to_json`
- Produces: `OPTIONAL` includes `user_agent`, `devicetype`, `clientversion`, `wxtoken`, `slave_sid`, `data_ticket`; `normalize_credentials` keeps those keys when present

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty file).

Create `tests/test_credentials.py`:

```python
import unittest

from app.credentials import (
    OPTIONAL,
    credentials_enough,
    credentials_to_json,
    normalize_credentials,
)


class CredentialsFingerprintTests(unittest.TestCase):
    def test_enough_still_only_requires_biz_uin_key(self):
        self.assertTrue(
            credentials_enough({"__biz": "b", "uin": "1", "key": "k"})
        )

    def test_normalize_keeps_fingerprint_keys(self):
        cred = normalize_credentials(
            {
                "__biz": "b",
                "uin": "1",
                "key": "k",
                "user_agent": "MicroMessenger/8.0",
                "devicetype": "windowswechat",
                "clientversion": "0x63090a13",
                "wxtoken": "wt",
                "slave_sid": "sid",
                "data_ticket": "dt",
                "noise": "drop-me",
            }
        )
        self.assertEqual(cred["user_agent"], "MicroMessenger/8.0")
        self.assertEqual(cred["devicetype"], "windowswechat")
        self.assertEqual(cred["clientversion"], "0x63090a13")
        self.assertEqual(cred["slave_sid"], "sid")
        self.assertEqual(cred["data_ticket"], "dt")
        self.assertNotIn("noise", cred)

    def test_normalize_drops_empty_optional(self):
        cred = normalize_credentials(
            {"__biz": "b", "uin": "1", "key": "k", "user_agent": "  "}
        )
        self.assertNotIn("user_agent", cred)

    def test_json_includes_fingerprint_when_present(self):
        text = credentials_to_json(
            {"__biz": "b", "uin": "1", "key": "k", "user_agent": "UA"}
        )
        self.assertIn("user_agent", text)
        self.assertIn("UA", text)

    def test_optional_declares_new_keys(self):
        for key in (
            "user_agent",
            "devicetype",
            "clientversion",
            "wxtoken",
            "slave_sid",
            "data_ticket",
        ):
            self.assertIn(key, OPTIONAL)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_credentials -v`

Expected: FAIL on `test_optional_declares_new_keys` and/or `test_normalize_keeps_fingerprint_keys` (`user_agent` missing).

- [ ] **Step 3: Write minimal implementation**

In `app/credentials.py` replace the key constants:

```python
REQUIRED = ("__biz", "uin", "key")
OPTIONAL = (
    "pass_ticket",
    "appmsg_token",
    "wxtoken",
    "user_agent",
    "devicetype",
    "clientversion",
    "slave_sid",
    "data_ticket",
)
ALL_KEYS = REQUIRED + OPTIONAL
```

Leave `normalize_credentials` / `credentials_to_json` as they already iterate `ALL_KEYS`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_credentials -v`

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/test_credentials.py app/credentials.py
git commit -m "feat: 凭证可选字段支持客户端指纹"
```

---

### Task 2: MITM capture writes fingerprint through the inbox

**Files:**
- Modify: `app/mitm_addon.py`
- Modify: `app/mitm_capture.py` (`read_new_credentials` key filter)
- Test: `tests/test_mitm_fingerprint.py` (create)

**Interfaces:**
- Consumes: Task 1 `OPTIONAL` keys; existing `_merge_from_url` / `_save`
- Produces:
  - `extract_request_fingerprint(url: str, headers: Any) -> dict[str, str]`
  - `INBOX_CRED_KEYS`: tuple of keys the inbox reader keeps
  - `_save` writes fingerprint keys when non-empty
  - `MitmCaptureService.read_new_credentials` returns those keys

- [ ] **Step 1: Write the failing test**

Create `tests/test_mitm_fingerprint.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.mitm_addon import extract_request_fingerprint
from app.mitm_capture import MitmCaptureService


class _Hdr(dict):
    def get(self, key, default=""):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class ExtractFingerprintTests(unittest.TestCase):
    def test_extracts_ua_query_and_cookies(self):
        url = (
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg"
            "&__biz=MzA%3D&devicetype=WindowsWechat"
            "&clientversion=0x63090a13&wxtoken=77"
        )
        headers = _Hdr(
            {
                "User-Agent": "WindowsWechat UA",
                "Cookie": "pass_ticket=pt; slave_sid=sid1; data_ticket=dt1; extra=no",
            }
        )
        fp = extract_request_fingerprint(url, headers)
        self.assertEqual(fp["user_agent"], "WindowsWechat UA")
        self.assertEqual(fp["devicetype"], "WindowsWechat")
        self.assertEqual(fp["clientversion"], "0x63090a13")
        self.assertEqual(fp["wxtoken"], "77")
        self.assertEqual(fp["slave_sid"], "sid1")
        self.assertEqual(fp["data_ticket"], "dt1")
        self.assertNotIn("extra", fp)

    def test_missing_headers_returns_empty(self):
        self.assertEqual(extract_request_fingerprint("", None), {})


class InboxReaderTests(unittest.TestCase):
    def test_read_new_credentials_keeps_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inbox = root / "data" / "capture_inbox.jsonl"
            inbox.parent.mkdir()
            row = {
                "__biz": "b",
                "uin": "1",
                "key": "k",
                "pass_ticket": "pt",
                "user_agent": "UA-1",
                "clientversion": "0x1",
                "slave_sid": "sid",
            }
            inbox.write_text(json.dumps(row) + "\n", encoding="utf-8")
            svc = MitmCaptureService(root)
            svc._inbox_offset = 0
            got = svc.read_new_credentials(consume=True)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["user_agent"], "UA-1")
            self.assertEqual(got[0]["clientversion"], "0x1")
            self.assertEqual(got[0]["slave_sid"], "sid")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_mitm_fingerprint -v`

Expected: FAIL — `extract_request_fingerprint` is not defined; inbox reader drops `user_agent`.

- [ ] **Step 3: Write minimal implementation**

In `app/mitm_addon.py`:

1. After `KEYS = (...)` add:

```python
FINGERPRINT_QUERY_KEYS = ("devicetype", "clientversion", "wxtoken")
FINGERPRINT_COOKIE_KEYS = ("slave_sid", "data_ticket")
```

2. Add this function (near the other merge helpers):

```python
def extract_request_fingerprint(url: str, headers) -> dict[str, str]:
    """Pull UA / device fields / extra WeChat cookies from one MP request."""
    out: dict[str, str] = {}
    if headers is not None:
        try:
            ua = headers.get("User-Agent", "") or ""
        except Exception:
            ua = ""
        if str(ua).strip():
            out["user_agent"] = str(ua).strip()
        try:
            cookie = headers.get("Cookie", "") or ""
        except Exception:
            cookie = ""
        for part in str(cookie).split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            k, _, v = part.partition("=")
            k = k.strip()
            if k in FINGERPRINT_COOKIE_KEYS and v.strip():
                out[k] = unquote(v.strip())
    if url:
        try:
            q = parse_qs(urlparse(url).query)
        except Exception:
            q = {}
        for k in FINGERPRINT_QUERY_KEYS:
            vals = q.get(k) or []
            if vals and vals[0]:
                out[k] = unquote(vals[0])
    return {k: v for k, v in out.items() if v}
```

3. In `CredentialCapture.request`, after merging URL/cookie into `bucket` and before `_enough` / `_save`, merge fingerprint:

```python
        fp = extract_request_fingerprint(url, headers)
        if fp:
            bucket.update(fp)
            changed = True
```

Place this after `changed = _merge_from_cookie(...)` and after `biz` attribution (so we only attach fingerprint to a known `__biz` bucket).

4. Change `_save` to persist non-empty fingerprint keys:

```python
def _save(cred: dict[str, str]) -> None:
    path = _inbox()
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = (
        "user_agent",
        "devicetype",
        "clientversion",
        "wxtoken",
        "slave_sid",
        "data_ticket",
    )
    payload = {
        **{k: cred.get(k, "") for k in KEYS},
        **{k: cred[k] for k in extra if cred.get(k)},
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "mitm",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"[schinza-capture] saved → {path}")
    _debug_log(f"凭证已保存 __biz={str(cred.get('__biz') or '')[:20]}")
```

In `app/mitm_capture.py` `read_new_credentials`, replace the hard-coded key tuple:

```python
            keep = (
                "__biz",
                "uin",
                "key",
                "pass_ticket",
                "appmsg_token",
                "wxtoken",
                "user_agent",
                "devicetype",
                "clientversion",
                "slave_sid",
                "data_ticket",
            )
            creds.append({k: str(data.get(k) or "") for k in keep if data.get(k)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_mitm_fingerprint tests.test_credentials -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/mitm_addon.py app/mitm_capture.py tests/test_mitm_fingerprint.py
git commit -m "feat: 抓包写入 UA 与设备指纹"
```

---

### Task 3: Safer single-account getmsg + `stopped_reason`

**Files:**
- Modify: `app/history_client.py`
- Test: `tests/test_history_stop.py` (create)

**Interfaces:**
- Consumes: fingerprint keys on `cred`; existing `fetch_getmsg_page` / `fetch_history_days`
- Produces:
  - `DEFAULT_UA` constant (current hardcoded UA string)
  - `DEFAULT_PAGE_COUNT = 8`
  - `fetch_history_days` defaults: `sleep_s=3.4`, `sleep_jitter=0.32`, `cooldown_every=4`, `cooldown_extra_s=10.0`, `count=8`
  - `is_rate_limit_error(err: str) -> bool`
  - `classify_stopped_reason(err: str, *, cancelled: bool = False, ok: bool = False) -> str`
  - `build_getmsg_headers(cred, biz: str) -> dict[str, str]`
  - `build_getmsg_cookies(cred) -> dict[str, str]`
  - every `fetch_history_days` return dict includes `stopped_reason`: `rate_limited` | `expired` | `network` | `cancelled` | `completed`

- [ ] **Step 1: Write the failing test**

Create `tests/test_history_stop.py`:

```python
import inspect
import unittest

from app.history_client import (
    DEFAULT_PAGE_COUNT,
    classify_stopped_reason,
    fetch_history_days,
    is_rate_limit_error,
    build_getmsg_cookies,
    build_getmsg_headers,
)


class ClassifyStopTests(unittest.TestCase):
    def test_rate_limited_unknownerror(self):
        self.assertTrue(is_rate_limit_error("微信风控拒绝（unknownerror）"))
        self.assertEqual(
            classify_stopped_reason("unknownerror"), "rate_limited"
        )

    def test_rate_limited_freq(self):
        self.assertEqual(classify_stopped_reason("操作频繁 freq"), "rate_limited")

    def test_expired(self):
        self.assertEqual(classify_stopped_reason("凭证已失效：过期"), "expired")
        self.assertEqual(classify_stopped_reason("缺少字段: key"), "expired")

    def test_network(self):
        self.assertEqual(
            classify_stopped_reason("Timeout: 连接微信超时"), "network"
        )

    def test_cancelled_and_completed(self):
        self.assertEqual(
            classify_stopped_reason("已取消", cancelled=True), "cancelled"
        )
        self.assertEqual(classify_stopped_reason("", ok=True), "completed")


class FingerprintRequestTests(unittest.TestCase):
    def test_headers_use_captured_ua(self):
        headers = build_getmsg_headers(
            {"user_agent": "Captured-UA"}, biz="MzA="
        )
        self.assertEqual(headers["User-Agent"], "Captured-UA")

    def test_headers_fallback_default_ua(self):
        headers = build_getmsg_headers({}, biz="MzA=")
        self.assertIn("MicroMessenger", headers["User-Agent"])

    def test_cookies_include_optional_tickets(self):
        cookies = build_getmsg_cookies(
            {
                "uin": "123",
                "pass_ticket": "pt",
                "slave_sid": "sid",
                "data_ticket": "dt",
            }
        )
        self.assertEqual(cookies["wxuin"], "123")
        self.assertEqual(cookies["pass_ticket"], "pt")
        self.assertEqual(cookies["slave_sid"], "sid")
        self.assertEqual(cookies["data_ticket"], "dt")


class HistoryDefaultsTests(unittest.TestCase):
    def test_page_count_is_eight(self):
        self.assertEqual(DEFAULT_PAGE_COUNT, 8)

    def test_fetch_history_days_default_pacing(self):
        params = inspect.signature(fetch_history_days).parameters
        self.assertEqual(params["sleep_s"].default, 3.4)
        self.assertEqual(params["sleep_jitter"].default, 0.32)
        self.assertEqual(params["cooldown_every"].default, 4)
        self.assertEqual(params["cooldown_extra_s"].default, 10.0)
        self.assertEqual(params["count"].default, 8)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_history_stop -v`

Expected: FAIL — missing symbols / `DEFAULT_PAGE_COUNT` still 10 / old sleep defaults.

- [ ] **Step 3: Write minimal implementation**

In `app/history_client.py`:

1. Change `DEFAULT_PAGE_COUNT = 8`.

2. Add after `GETMSG_URL`:

```python
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "WindowsWechat(0x63090a13) XWEB/11275"
)
```

3. Extend `normalize_credentials` unquote list with `user_agent`, `devicetype`, `clientversion`, `slave_sid`, `data_ticket`.

4. Add helpers (replace `_rate_limit_hint` body to call `is_rate_limit_error`):

```python
def is_rate_limit_error(err: str) -> bool:
    low = (err or "").lower()
    return any(
        k in low
        for k in ("freq", "频繁", "操作频繁", "unknownerror", "风控")
    )


def classify_stopped_reason(
    err: str, *, cancelled: bool = False, ok: bool = False
) -> str:
    if cancelled:
        return "cancelled"
    if ok:
        return "completed"
    if is_rate_limit_error(err):
        return "rate_limited"
    low = (err or "").lower()
    if any(k in low for k in ("invalid", "失效", "过期", "缺少字段")):
        return "expired"
    return "network"


def build_getmsg_headers(cred: dict[str, Any], *, biz: str) -> dict[str, str]:
    ua = str(cred.get("user_agent") or "").strip() or DEFAULT_UA
    return {
        "User-Agent": ua,
        "Referer": (
            f"https://mp.weixin.qq.com/mp/profile_ext?action=home"
            f"&__biz={biz}&scene=124#wechat_redirect"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }


def build_getmsg_cookies(cred: dict[str, Any]) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if cred.get("pass_ticket"):
        cookies["pass_ticket"] = str(cred["pass_ticket"]).strip()
    if cred.get("uin"):
        cookies["wxuin"] = str(cred["uin"]).strip()
    if cred.get("slave_sid"):
        cookies["slave_sid"] = str(cred["slave_sid"]).strip()
    if cred.get("data_ticket"):
        cookies["data_ticket"] = str(cred["data_ticket"]).strip()
    return cookies


def _rate_limit_hint(err: str) -> str:
    if is_rate_limit_error(err):
        return "（疑似被微信限流：建议暂停几分钟，降低拉取频率后再试）"
    return ""
```

5. In `fetch_getmsg_page`, replace the inline headers/cookies with:

```python
    headers = build_getmsg_headers(cred, biz=params["__biz"])
    cookies = build_getmsg_cookies(cred)
```

Keep `devicetype` / `clientversion` / `wxtoken` params as they already read from `cred`.

6. Change `fetch_history_days` signature defaults:

```python
    sleep_s: float = 3.4,
    sleep_jitter: float = 0.32,
    cooldown_every: int = 4,
    cooldown_extra_s: float = 10.0,
```

and `count: int = DEFAULT_PAGE_COUNT` (already).

7. Add `stopped_reason` to every return of `fetch_history_days`:

- cancel branch: `"stopped_reason": "cancelled"`
- page error branch: `"stopped_reason": classify_stopped_reason(err_text)`
- success return: `"stopped_reason": "completed"`

Do **not** add a retry around `unknownerror`. Existing `_get_page_with_retry` only retries Timeout/ConnectionError.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_history_stop tests.test_credentials -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/history_client.py tests/test_history_stop.py
git commit -m "fix: getmsg 放慢翻页并回放客户端指纹"
```

---

### Task 4: Serial batch orchestrator

**Files:**
- Create: `app/history_batch.py`
- Test: `tests/test_history_batch.py` (create)

**Interfaces:**
- Consumes: `fetch_history_days`, `classify_stopped_reason`, credentials enough check
- Produces:

```python
def fetch_history_batch(
    accounts: list[dict[str, Any]],
    *,
    days: int | None = 7,
    start_ts: int | None = None,
    end_ts: int | None = None,
    on_progress: Callable[[int, int, str, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    fetch_one: Callable[..., dict[str, Any]] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    between_s: tuple[float, float] = (6.0, 10.0),
    extra_after_rate_limit_s: float = 15.0,
    sightings_for: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
```

Each account dict: `id`, `name`, `credentials`, optional `active` (default True).

Return:

```python
{
  "ok": True,
  "cancelled": False,
  "groups": [
    {
      "account_id": str,
      "name": str,
      "articles": list,
      "pages": int,
      "status": "completed"|"rate_limited"|"expired"|"failed"|"cancelled",
      "error": str,
      "stopped_reason": str,
    }
  ],
  "summary": {
    "completed": int,
    "rate_limited": int,
    "expired": int,
    "failed": int,
    "cancelled": int,
    "articles": int,
  },
}
```

Status mapping from a single fetch:

- `active is False` or missing `__biz/uin/key` → `expired`, no `fetch_one` call
- `stopped_reason == cancelled` → `cancelled`
- `stopped_reason == rate_limited` → `rate_limited`
- `stopped_reason == expired` → `expired`
- `stopped_reason == completed` and `ok` → `completed`
- else → `failed`

Gap before account index `i>0`: uniform random in `between_s`; if previous group's `stopped_reason == rate_limited`, add `extra_after_rate_limit_s`. Skip the gap if `should_cancel()` is already true.

- [ ] **Step 1: Write the failing test**

Create `tests/test_history_batch.py`:

```python
import unittest

from app.history_batch import fetch_history_batch


def _acc(i: str, *, active: bool = True, cred: bool = True) -> dict:
    credentials = {"__biz": f"b{i}", "uin": "1", "key": "k"} if cred else {}
    return {
        "id": i,
        "name": f"号{i}",
        "credentials": credentials,
        "active": active,
    }


class HistoryBatchTests(unittest.TestCase):
    def test_skips_inactive_then_fetches_next(self):
        calls: list[str] = []

        def fetch_one(cred, **_kw):
            calls.append(cred["__biz"])
            return {
                "ok": True,
                "articles": [{"title": "t", "identity": cred["__biz"]}],
                "pages": 1,
                "stopped_reason": "completed",
            }

        sleeps: list[float] = []
        result = fetch_history_batch(
            [_acc("1", active=False), _acc("2")],
            fetch_one=fetch_one,
            sleep_fn=sleeps.append,
            between_s=(0.0, 0.0),
            extra_after_rate_limit_s=0.0,
        )
        self.assertEqual(calls, ["b2"])
        self.assertEqual(result["groups"][0]["status"], "expired")
        self.assertEqual(result["groups"][1]["status"], "completed")
        self.assertEqual(result["summary"]["expired"], 1)
        self.assertEqual(result["summary"]["completed"], 1)
        self.assertEqual(result["summary"]["articles"], 1)

    def test_rate_limit_keeps_articles_and_continues(self):
        def fetch_one(cred, **_kw):
            if cred["__biz"] == "b1":
                return {
                    "ok": False,
                    "articles": [{"title": "partial", "identity": "p"}],
                    "pages": 2,
                    "error": "unknownerror",
                    "stopped_reason": "rate_limited",
                }
            return {
                "ok": True,
                "articles": [{"title": "ok", "identity": "o"}],
                "pages": 1,
                "stopped_reason": "completed",
            }

        sleeps: list[float] = []
        result = fetch_history_batch(
            [_acc("1"), _acc("2")],
            fetch_one=fetch_one,
            sleep_fn=sleeps.append,
            between_s=(3.0, 3.0),
            extra_after_rate_limit_s=15.0,
        )
        self.assertEqual(result["groups"][0]["status"], "rate_limited")
        self.assertEqual(len(result["groups"][0]["articles"]), 1)
        self.assertEqual(result["groups"][1]["status"], "completed")
        self.assertTrue(any(s >= 18.0 for s in sleeps))

    def test_cancel_skips_remaining_without_fetch(self):
        calls: list[str] = []
        cancelled = {"n": 0}

        def should_cancel():
            return cancelled["n"] >= 1

        def fetch_one(cred, **_kw):
            calls.append(cred["__biz"])
            cancelled["n"] += 1
            return {
                "ok": False,
                "cancelled": True,
                "articles": [],
                "pages": 0,
                "error": "已取消",
                "stopped_reason": "cancelled",
            }

        result = fetch_history_batch(
            [_acc("1"), _acc("2"), _acc("3")],
            fetch_one=fetch_one,
            should_cancel=should_cancel,
            sleep_fn=lambda _s: None,
            between_s=(0.0, 0.0),
        )
        self.assertEqual(calls, ["b1"])
        self.assertEqual(result["groups"][1]["status"], "cancelled")
        self.assertEqual(result["groups"][2]["status"], "cancelled")
        self.assertTrue(result["cancelled"])
        self.assertTrue(result["ok"])

    def test_progress_callback_indexes(self):
        seen: list[tuple[int, int, str]] = []

        def fetch_one(_cred, **kw):
            cb = kw.get("on_progress")
            if cb:
                cb("第 1 页")
            return {"ok": True, "articles": [], "pages": 1, "stopped_reason": "completed"}

        fetch_history_batch(
            [_acc("1"), _acc("2")],
            fetch_one=fetch_one,
            on_progress=lambda i, n, name, msg: seen.append((i, n, name)),
            sleep_fn=lambda _s: None,
            between_s=(0.0, 0.0),
        )
        self.assertEqual(seen[0], (1, 2, "号1"))
        self.assertEqual(seen[-1][0], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_history_batch -v`

Expected: FAIL — `app.history_batch` missing.

- [ ] **Step 3: Write minimal implementation**

Create `app/history_batch.py`:

```python
"""Queue history fetches across accounts (one at a time)."""

from __future__ import annotations

import random
from typing import Any, Callable

from app.history_client import classify_stopped_reason, fetch_history_days, validate_credentials

ProgressCb = Callable[[int, int, str, str], None]
FetchOne = Callable[..., dict[str, Any]]


def _status_from_result(result: dict[str, Any]) -> str:
    reason = str(result.get("stopped_reason") or "")
    if reason == "cancelled" or result.get("cancelled"):
        return "cancelled"
    if reason == "rate_limited":
        return "rate_limited"
    if reason == "expired":
        return "expired"
    if reason == "completed" and result.get("ok"):
        return "completed"
    return "failed"


def _empty_group(
    account: dict[str, Any],
    *,
    status: str,
    error: str,
    stopped_reason: str,
) -> dict[str, Any]:
    return {
        "account_id": str(account.get("id") or ""),
        "name": str(account.get("name") or "未命名公众号"),
        "articles": [],
        "pages": 0,
        "status": status,
        "error": error,
        "stopped_reason": stopped_reason,
    }


def fetch_history_batch(
    accounts: list[dict[str, Any]],
    *,
    days: int | None = 7,
    start_ts: int | None = None,
    end_ts: int | None = None,
    on_progress: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
    fetch_one: FetchOne | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    between_s: tuple[float, float] = (6.0, 10.0),
    extra_after_rate_limit_s: float = 15.0,
    sightings_for: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    worker = fetch_one or fetch_history_days
    pause = sleep_fn or (lambda s: __import__("time").sleep(s))
    groups: list[dict[str, Any]] = []
    cancelled = False
    prev_reason = ""
    total = len(accounts)

    for idx, account in enumerate(accounts):
        name = str(account.get("name") or "未命名公众号")
        if should_cancel and should_cancel() and groups:
            cancelled = True
            for rest in accounts[idx:]:
                groups.append(
                    _empty_group(
                        rest,
                        status="cancelled",
                        error="已取消",
                        stopped_reason="cancelled",
                    )
                )
            break

        if idx > 0 and not (should_cancel and should_cancel()):
            lo, hi = between_s
            delay = random.uniform(min(lo, hi), max(lo, hi))
            if prev_reason == "rate_limited":
                delay += max(0.0, extra_after_rate_limit_s)
            if delay > 0:
                pause(delay)

        if should_cancel and should_cancel() and idx > 0:
            cancelled = True
            for rest in accounts[idx:]:
                groups.append(
                    _empty_group(
                        rest,
                        status="cancelled",
                        error="已取消",
                        stopped_reason="cancelled",
                    )
                )
            break

        cred = dict(account.get("credentials") or {})
        active = account.get("active", True)
        ok_cred, cred_err = validate_credentials(cred)
        if not active or not ok_cred:
            group = _empty_group(
                account,
                status="expired",
                error=cred_err or "凭证过期，请续约",
                stopped_reason="expired",
            )
            groups.append(group)
            prev_reason = "expired"
            continue

        def _page_progress(msg: str, _idx=idx, _name=name) -> None:
            if on_progress:
                on_progress(_idx + 1, total, _name, msg)

        biz = str(cred.get("__biz") or "")
        sightings = sightings_for(biz) if sightings_for else None
        result = worker(
            cred,
            days=days,
            start_ts=start_ts,
            end_ts=end_ts,
            on_progress=_page_progress,
            should_cancel=should_cancel,
            sightings=sightings,
        )
        if result.get("cancelled"):
            cancelled = True
        reason = str(
            result.get("stopped_reason")
            or classify_stopped_reason(
                str(result.get("error") or ""),
                cancelled=bool(result.get("cancelled")),
                ok=bool(result.get("ok")),
            )
        )
        status = _status_from_result({**result, "stopped_reason": reason})
        groups.append(
            {
                "account_id": str(account.get("id") or ""),
                "name": name,
                "articles": list(result.get("articles") or []),
                "pages": int(result.get("pages") or 0),
                "status": status,
                "error": str(result.get("error") or ""),
                "stopped_reason": reason,
            }
        )
        prev_reason = reason
        if cancelled:
            for rest in accounts[idx + 1 :]:
                groups.append(
                    _empty_group(
                        rest,
                        status="cancelled",
                        error="已取消",
                        stopped_reason="cancelled",
                    )
                )
            break

    summary = {
        "completed": 0,
        "rate_limited": 0,
        "expired": 0,
        "failed": 0,
        "cancelled": 0,
        "articles": 0,
    }
    for g in groups:
        st = str(g.get("status") or "failed")
        if st in summary:
            summary[st] += 1
        else:
            summary["failed"] += 1
        summary["articles"] += len(g.get("articles") or [])

    return {
        "ok": True,
        "cancelled": cancelled,
        "groups": groups,
        "summary": summary,
    }
```

Fix the first-account cancel: `test_cancel_skips_remaining` sets `should_cancel` true only after the first fetch returns. The loop must not treat "cancel before any group" as skipping account 1. The `if should_cancel and groups:` guard handles that. After first fetch, `cancelled` is True and remaining are appended — that matches the test (`calls == ["b1"]`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_history_batch -v`

Expected: PASS. If the cancel/gap test fails, adjust only the loop order: **gap → cancel check → fetch**. Do not fetch remaining accounts after cancel.

- [ ] **Step 5: Commit**

```bash
git add app/history_batch.py tests/test_history_batch.py
git commit -m "feat: 多公众号历史排队拉取编排"
```

---

### Task 5: Batch UI helpers (no widgets)

**Files:**
- Create: `app/history_batch_ui.py`
- Test: `tests/test_history_batch_ui.py` (create)

**Interfaces:**
- Consumes: group/summary dicts from Task 4
- Produces:

```python
def default_selected_ids(rows: list[dict[str, Any]]) -> list[str]:
    """Active accounts with __biz/uin/key, in list order."""

def group_status_label(status: str, article_count: int, error: str = "") -> str:
def group_status_color_key(status: str) -> str:  # "ok"|"warn"|"muted"|"danger"
def format_batch_progress(index: int, total: int, name: str, page_msg: str) -> str:
def format_batch_summary(summary: dict[str, int]) -> str:
```

Copy (exact):

- `completed` → `完成`
- `rate_limited` → `被风控跳过，已保留 {n} 篇`
- `expired` → `凭证过期，请续约`
- `failed` → `失败：{error}` if error else `失败`
- `cancelled` → `已取消`
- progress → `{index}/{total} 「{name}」{page_msg}`
- summary → `完成 8 · 风控跳过 3 · 过期 1 · 共 142 篇`  
  Omit a segment when its count is 0, except always keep `共 N 篇`.

Color keys: completed=`ok`, rate_limited=`warn`, expired=`muted`, cancelled=`muted`, failed=`danger`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_history_batch_ui.py`:

```python
import unittest

from app.history_batch_ui import (
    default_selected_ids,
    format_batch_progress,
    format_batch_summary,
    group_status_color_key,
    group_status_label,
)


class BatchUiHelperTests(unittest.TestCase):
    def test_default_selected_only_active_complete(self):
        rows = [
            {
                "id": "a",
                "active": True,
                "credentials": {"__biz": "1", "uin": "1", "key": "k"},
            },
            {"id": "b", "active": False, "credentials": {"__biz": "1", "uin": "1", "key": "k"}},
            {"id": "c", "active": True, "credentials": {}},
        ]
        self.assertEqual(default_selected_ids(rows), ["a"])

    def test_labels_and_colors(self):
        self.assertEqual(group_status_label("completed", 3), "完成")
        self.assertEqual(
            group_status_label("rate_limited", 5), "被风控跳过，已保留 5 篇"
        )
        self.assertEqual(group_status_label("expired", 0), "凭证过期，请续约")
        self.assertEqual(group_status_label("cancelled", 0), "已取消")
        self.assertEqual(group_status_label("failed", 0, "SSL 错误"), "失败：SSL 错误")
        self.assertEqual(group_status_color_key("rate_limited"), "warn")
        self.assertEqual(group_status_color_key("expired"), "muted")
        self.assertEqual(group_status_color_key("failed"), "danger")
        self.assertEqual(group_status_color_key("completed"), "ok")

    def test_progress_and_summary(self):
        self.assertEqual(
            format_batch_progress(3, 12, "校园号", "第 2 页"),
            "3/12 「校园号」第 2 页",
        )
        self.assertEqual(
            format_batch_summary(
                {
                    "completed": 8,
                    "rate_limited": 3,
                    "expired": 1,
                    "failed": 0,
                    "cancelled": 0,
                    "articles": 142,
                }
            ),
            "完成 8 · 风控跳过 3 · 过期 1 · 共 142 篇",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_history_batch_ui -v`

Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Create `app/history_batch_ui.py`:

```python
"""Pure helpers for the History-tab batch UI."""

from __future__ import annotations

from typing import Any


def default_selected_ids(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if not row.get("active", True):
            continue
        cred = row.get("credentials") or {}
        if cred.get("__biz") and cred.get("uin") and cred.get("key"):
            out.append(str(row.get("id") or ""))
    return [i for i in out if i]


def group_status_label(status: str, article_count: int, error: str = "") -> str:
    if status == "completed":
        return "完成"
    if status == "rate_limited":
        return f"被风控跳过，已保留 {int(article_count)} 篇"
    if status == "expired":
        return "凭证过期，请续约"
    if status == "cancelled":
        return "已取消"
    err = (error or "").strip()
    return f"失败：{err}" if err else "失败"


def group_status_color_key(status: str) -> str:
    return {
        "completed": "ok",
        "rate_limited": "warn",
        "expired": "muted",
        "cancelled": "muted",
        "failed": "danger",
    }.get(status, "muted")


def format_batch_progress(index: int, total: int, name: str, page_msg: str) -> str:
    return f"{int(index)}/{int(total)} 「{name}」{page_msg}"


def format_batch_summary(summary: dict[str, int]) -> str:
    parts: list[str] = []
    mapping = (
        ("completed", "完成"),
        ("rate_limited", "风控跳过"),
        ("expired", "过期"),
        ("failed", "失败"),
        ("cancelled", "取消"),
    )
    for key, label in mapping:
        n = int(summary.get(key) or 0)
        if n:
            parts.append(f"{label} {n}")
    parts.append(f"共 {int(summary.get('articles') or 0)} 篇")
    return " · ".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_history_batch_ui -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/history_batch_ui.py tests/test_history_batch_ui.py
git commit -m "feat: 批量拉取界面文案与勾选辅助函数"
```

---

### Task 6: History tab — checkboxes, batch button, grouped results

**Files:**
- Modify: `app/ui.py`
- Manual test only (no Tk unit tests)

**Interfaces:**
- Consumes: `fetch_history_batch`, `format_batch_progress`, `format_batch_summary`, `default_selected_ids`, `group_status_label`, `group_status_color_key`, `fetch_history_days` (unchanged single-account path)
- Produces: History tab widgets and handlers listed below

State to add on `App.__init__` (near the other `_history_*` fields):

```python
        self._batch_selected: set[str] = set()
        self._batch_check_vars: dict[str, ctk.BooleanVar] = {}
        self._history_groups: list[dict[str, Any]] = []
        self._history_active_group_id: str | None = None
        self._batch_fetching = False
```

`_history_fetching` remains the lock for **both** single and batch (disable both buttons while either runs).

- [ ] **Step 1: Import helpers**

At the top of `app/ui.py` add:

```python
from app.history_batch import fetch_history_batch
from app.history_batch_ui import (
    default_selected_ids,
    format_batch_progress,
    format_batch_summary,
    group_status_color_key,
    group_status_label,
)
```

- [ ] **Step 2: Extend `_build_history_panel`**

After the existing single-account row (row 2) and **before** `self.hist_status`, insert two rows. Shift current status to row 5, list tools to row 6, article tools to row 7.

Row 3 — checkbox host:

```python
        self.batch_pick_frame = ctk.CTkScrollableFrame(
            panel,
            fg_color=COLORS["card"],
            height=120,
            corner_radius=10,
        )
        self.batch_pick_frame.grid(
            row=3, column=0, columnspan=4, sticky="ew", padx=18, pady=(4, 4)
        )
        self.batch_pick_frame.grid_columnconfigure(0, weight=1)
```

Row 4 — batch actions:

```python
        batch_pick_tools = ctk.CTkFrame(panel, fg_color="transparent")
        batch_pick_tools.grid(
            row=4, column=0, columnspan=4, sticky="ew", padx=18, pady=(0, 4)
        )
        ctk.CTkButton(
            batch_pick_tools, text="全选有效", width=88, height=32,
            corner_radius=8, fg_color=COLORS["border"], hover_color="#3a4a5e",
            command=self.select_all_batch_accounts,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            batch_pick_tools, text="清空", width=64, height=32,
            corner_radius=8, fg_color=COLORS["border"], hover_color="#3a4a5e",
            command=self.clear_batch_account_selection,
        ).pack(side="left", padx=(0, 10))
        self.hist_batch_btn = ctk.CTkButton(
            batch_pick_tools, text="批量拉取", width=96, height=32,
            corner_radius=8, fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color="#052e16",
            font=ctk.CTkFont(family=UI_FONT, size=12, weight="bold"),
            command=self.start_history_batch_fetch,
        )
        self.hist_batch_btn.pack(side="left")
```

Renumber `hist_status` to row 5, `list_tools` to row 6, `batch_tools` to row 7.

In `list_wrap` (article list), insert a group bar above the scroll list:

```python
        self.hist_groups = ctk.CTkFrame(list_wrap, fg_color="transparent")
        self.hist_groups.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.hist_list.grid(row=2, column=0, sticky="nsew")
        list_wrap.grid_rowconfigure(2, weight=1)
```

Keep the "文章列表" label on row 0.

- [ ] **Step 3: Rebuild checkbox list**

Add methods (near `refresh_history_account_options`). When refreshing, include **all** store accounts for the checkbox list; single-account dropdown stays active-only.

```python
    def _batch_account_rows(self) -> list[dict[str, Any]]:
        self.store.mark_expired_if_needed()
        rows: list[dict[str, Any]] = []
        for row in self.store.list_accounts():
            aid = str(row.get("id") or "")
            cred = row.get("credentials") or {}
            active = self.store.is_active(aid)
            rows.append(
                {
                    "id": aid,
                    "name": row.get("name") or "未命名公众号",
                    "credentials": cred,
                    "active": active,
                }
            )
        return rows

    def refresh_batch_account_checks(self, *, reset_default: bool = False) -> None:
        rows = self._batch_account_rows()
        valid = {r["id"] for r in rows}
        if reset_default or not self._batch_selected:
            self._batch_selected = set(default_selected_ids(rows))
        else:
            self._batch_selected &= valid
        for child in self.batch_pick_frame.winfo_children():
            child.destroy()
        self._batch_check_vars.clear()
        if not rows:
            ctk.CTkLabel(
                self.batch_pick_frame,
                text="还没有公众号。请先在凭证管理里添加并抓包。",
                text_color=COLORS["muted"],
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return
        for i, row in enumerate(rows):
            aid = row["id"]
            label = str(row["name"])
            if not row["active"]:
                label += "（请续约）"
            var = ctk.BooleanVar(value=aid in self._batch_selected and row["active"])
            self._batch_check_vars[aid] = var

            def _toggle(v=var, account_id=aid, is_active=row["active"]) -> None:
                if not is_active:
                    v.set(False)
                    self._batch_selected.discard(account_id)
                    return
                if v.get():
                    self._batch_selected.add(account_id)
                else:
                    self._batch_selected.discard(account_id)

            box = ctk.CTkCheckBox(
                self.batch_pick_frame,
                text=label,
                variable=var,
                state="normal" if row["active"] else "disabled",
                command=_toggle,
                text_color=COLORS["text"] if row["active"] else COLORS["muted"],
                font=ctk.CTkFont(family=UI_FONT, size=12),
            )
            box.grid(row=i, column=0, sticky="w", padx=8, pady=2)

    def select_all_batch_accounts(self) -> None:
        self._batch_selected = set(default_selected_ids(self._batch_account_rows()))
        self.refresh_batch_account_checks()

    def clear_batch_account_selection(self) -> None:
        self._batch_selected.clear()
        self.refresh_batch_account_checks()
```

Call `refresh_batch_account_checks(reset_default=True)` once after `_build_history_panel` in `__init__` (or first time the history tab is shown). Also call `refresh_batch_account_checks()` from `refresh_history_account_options` without resetting the user's unchecks (`reset_default=False`).

On first history-tab visit, if `_batch_selected` is empty, `reset_default=True` so valid accounts start checked.

- [ ] **Step 4: Batch fetch / cancel / done**

```python
    def start_history_batch_fetch(self) -> None:
        if self._history_fetching:
            return
        self.refresh_history_account_options()
        rows = self._batch_account_rows()
        chosen = [r for r in rows if r["id"] in self._batch_selected]
        if not chosen:
            self.set_hist_status("请先勾选至少一个有效凭证公众号。", ok=False)
            return
        self._history_fetching = True
        self._batch_fetching = True
        self._history_cancel = False
        self.hist_fetch_btn.configure(state="disabled")
        self.hist_batch_btn.configure(
            state="normal", text="取消", command=self.cancel_history_fetch
        )
        self.set_hist_status(
            format_batch_progress(1, len(chosen), chosen[0]["name"], "准备中…"),
            ok=True,
        )

        start_ts = end_ts = None
        if self._history_range_iso:
            start_ts = _iso_date_to_ts(self._history_range_iso[0])
            end_ts = _iso_date_to_ts(self._history_range_iso[1], end_of_day=True)
        self.sightings.load()

        def worker() -> None:
            def progress(i: int, n: int, name: str, msg: str) -> None:
                text = format_batch_progress(i, n, name, msg)
                self.after(0, lambda t=text: self.set_hist_status(t, ok=True))

            try:
                result = fetch_history_batch(
                    chosen,
                    days=self._history_days,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    on_progress=progress,
                    should_cancel=lambda: self._history_cancel,
                    sightings_for=self.sightings.list_for_biz,
                )
            except Exception as exc:  # noqa: BLE001
                result = {
                    "ok": False,
                    "cancelled": False,
                    "groups": [],
                    "summary": {"articles": 0},
                    "error": describe_exception(exc),
                }
            self.after(0, lambda: self._on_history_batch_done(result))

        threading.Thread(target=worker, name="schinza-history-batch", daemon=True).start()

    def _on_history_batch_done(self, result: dict[str, Any]) -> None:
        self._history_fetching = False
        self._batch_fetching = False
        self.hist_fetch_btn.configure(
            state="normal", text=self._fetch_btn_label(), command=self.start_history_fetch
        )
        self.hist_batch_btn.configure(
            state="normal", text="批量拉取", command=self.start_history_batch_fetch
        )
        groups = list(result.get("groups") or [])
        self._history_groups = groups
        first = next((g for g in groups if g.get("articles")), groups[0] if groups else None)
        self._history_active_group_id = first.get("account_id") if first else None
        self._apply_active_group_articles()
        self._render_history_groups()
        if result.get("error") and not groups:
            self.set_hist_status(f"批量拉取失败：{result['error']}", ok=False)
            return
        self.set_hist_status(format_batch_summary(result.get("summary") or {}), ok=True)

    def _apply_active_group_articles(self) -> None:
        gid = self._history_active_group_id
        group = next((g for g in self._history_groups if g.get("account_id") == gid), None)
        if group is None:
            self._history_articles = []
            self._history_account_name = ""
            return
        self._history_articles = list(group.get("articles") or [])
        self._history_account_name = str(group.get("name") or "")
        self._history_selected.clear()
        self._render_history_list()

    def _render_history_groups(self) -> None:
        for child in self.hist_groups.winfo_children():
            child.destroy()
        if not self._history_groups:
            return
        for g in self._history_groups:
            aid = str(g.get("account_id") or "")
            selected = aid == self._history_active_group_id
            color_key = group_status_color_key(str(g.get("status") or ""))
            border = COLORS["accent"] if selected else COLORS[color_key] if color_key in COLORS else COLORS["border"]
            btn = ctk.CTkButton(
                self.hist_groups,
                text=(
                    f"{g.get('name')} · {len(g.get('articles') or [])} 篇 · "
                    f"{group_status_label(str(g.get('status') or ''), len(g.get('articles') or []), str(g.get('error') or ''))}"
                ),
                height=30,
                corner_radius=8,
                fg_color=COLORS["card"],
                hover_color="#3a4a5e",
                border_width=1,
                border_color=border,
                text_color=COLORS["text"],
                font=ctk.CTkFont(family=UI_FONT, size=12),
                command=lambda account_id=aid: self._select_history_group(account_id),
            )
            btn.pack(side="left", padx=(0, 8), pady=2)

    def _select_history_group(self, account_id: str) -> None:
        self._history_active_group_id = account_id
        self._apply_active_group_articles()
        self._render_history_groups()
```

Single-account `start_history_fetch` / `_on_history_done`: keep behavior, but clear `_history_groups` and call `_render_history_groups()` so leftover batch chips disappear. Disable `hist_batch_btn` while single fetch runs; `cancel_history_fetch` already sets `_history_cancel = True` — reuse it for batch.

When showing the history tab (`_show_tab("history")`), call `refresh_batch_account_checks()`.

- [ ] **Step 5: Run unit tests (regression)**

Run: `python -m unittest discover -s tests -v`

Expected: all PASS.

- [ ] **Step 6: Manual UI check**

1. Open History tab: valid accounts are checked; expired show `（请续约）` and cannot check.
2. Uncheck one → 清空 → 全选有效 restores only valid.
3. Single-account 拉取 still works (slower gaps).
4. 批量拉取 with ≥2 valid accounts: status like `1/2 「甲」正在拉取第 1 页…`; chips appear; click chip filters the list; 复制列表 / 导出列表 / 批量导出 use the visible group only.
5. Hit 取消 mid-batch: current account stops, later chips `已取消`.

- [ ] **Step 7: Commit**

```bash
git add app/ui.py
git commit -m "feat: 历史页支持勾选多号排队拉取"
```

---

### Task 7: Plan vs spec checklist (no extra features)

**Files:** none unless a gap was found during implementation

- [ ] **Step 1: Re-read the spec and tick coverage**

| Spec item | Task |
|---|---|
| Capture UA / device / slave_sid / data_ticket | 2 |
| Old creds without fingerprint still fetch (default UA) | 3 |
| Slower paging defaults | 3 |
| No retry on 风控 | 3 (unchanged retry scope) |
| `stopped_reason` | 3 |
| Serial batch + inter-account sleep + extra after 风控 | 4 |
| Skip expired, continue after 风控, cancel rest | 4 |
| Default-select valid, allow uncheck | 5+6 |
| Grouped results, export current group only | 6 |
| Summary line | 5+6 |
| `trust_env=False` | already in `fetch_history_days` |
| No true parallelism / no merged export / no body-export 风控 work | out of scope |

- [ ] **Step 2: Run full unittest suite**

Run: `python -m unittest discover -s tests -v`

Expected: PASS.

- [ ] **Step 3: Commit only if you fixed a gap**

Do not add README or version bump unless the user asks.

---

## Self-review

1. **Spec coverage:** All spec behaviors map to tasks 1–6. Non-goals are excluded.
2. **Placeholders:** None. Helpers, defaults, copy, and return shapes are specified.
3. **Type consistency:** `stopped_reason` and `status` strings are the same in Tasks 3–6. `fetch_history_batch` account shape is `id/name/credentials/active`. Progress callback is `(index, total, name, page_msg)`.

## Execution

After this plan is approved, implement task-by-task. Do not start Task N+1 until Task N tests pass and that task is committed.
