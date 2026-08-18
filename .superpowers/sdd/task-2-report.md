# Task 2 Report: MITM capture writes fingerprint through the inbox

## Status: DONE

## Summary

Implemented fingerprint extraction from MITM traffic (User-Agent, query params, cookies) and wired it through inbox save/read so downstream credential consumers receive the new optional fields.

## TDD Evidence

### Step 1 — RED (failing test)

Created `tests/test_mitm_fingerprint.py` with:
- `ExtractFingerprintTests.test_extracts_ua_query_and_cookies`
- `ExtractFingerprintTests.test_missing_headers_returns_empty`
- `InboxReaderTests.test_read_new_credentials_keeps_fingerprint`

Command:
```
python -m unittest tests.test_mitm_fingerprint -v
```

Output:
```
ImportError: cannot import name 'extract_request_fingerprint' from 'app.mitm_addon'
FAILED (errors=1)
```

### Step 2 — GREEN (implementation)

Changes:

**`app/mitm_addon.py`**
- Added `FINGERPRINT_QUERY_KEYS`, `FINGERPRINT_COOKIE_KEYS`
- Added `extract_request_fingerprint(url, headers) -> dict[str, str]`
- In `CredentialCapture.request`, merge fingerprint into bucket after URL/cookie merge and biz attribution
- Updated `_save` to persist non-empty fingerprint keys (`user_agent`, `devicetype`, `clientversion`, `wxtoken`, `slave_sid`, `data_ticket`)

**`app/mitm_capture.py`**
- Extended `read_new_credentials` key filter to include fingerprint fields

Command:
```
python -m unittest tests.test_mitm_fingerprint tests.test_credentials -v
```

Output:
```
test_extracts_ua_query_and_cookies ... ok
test_missing_headers_returns_empty ... ok
test_read_new_credentials_keeps_fingerprint ... ok
test_enough_still_only_requires_biz_uin_key ... ok
test_json_includes_fingerprint_when_present ... ok
test_normalize_drops_empty_optional ... ok
test_normalize_keeps_fingerprint_keys ... ok
test_optional_declares_new_keys ... ok

Ran 8 tests in 0.011s
OK
```

## Commit

```
78b4ca9 feat: 抓包写入 UA 与设备指纹
```

Files: `app/mitm_addon.py`, `app/mitm_capture.py`, `tests/test_mitm_fingerprint.py` (force-added)

## Concerns

None.

---

## Fix: fingerprint-only updates after first save (review finding)

### Problem

`_last_saved_fp` compared only `KEYS`; late-arriving fingerprint fields set `changed=True` but did not trigger `_save`.

### Change

**`app/mitm_addon.py`**
- Added `FINGERPRINT_KEYS` / `SAVED_FP_KEYS` (`KEYS` + fingerprint fields)
- `_last_saved_fp` now uses `SAVED_FP_KEYS` so fingerprint-only enrichment rewrites inbox
- `_save` reuses `FINGERPRINT_KEYS` (no raw Cookie header persisted)

**`tests/test_mitm_fingerprint.py`**
- Added `CredentialCaptureWriteTests.test_fingerprint_only_merge_triggers_second_inbox_write`

### Test command + result

```
python -m unittest tests.test_mitm_fingerprint tests.test_credentials -v
```

```
Ran 9 tests in 0.034s
OK
```

### Commit

```
fix: 指纹晚到时补写 inbox
```
