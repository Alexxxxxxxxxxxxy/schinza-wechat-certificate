<p align="center">
  <img src="assets/logo.png" alt="Schinza" width="128" height="128" />
</p>

<h1 align="center">Schinza</h1>

<p align="center">
  <a href="./README.md"><b>English</b></a> · <a href="./README.zh-CN.md">中文</a>
</p>

<p align="center">
  <strong>Windows desktop helper for WeChat Official Account credentials &amp; history</strong>
  <br />
  Capture short-lived MP keys · 30‑minute TTL · Fetch 7 / 30 / 90‑day, all, or custom‑day history · Export list &amp; full articles (HTML / Markdown / TXT / JSON / Word) · Batch import (CSV/TXT) · Batch export
</p>

<p align="center">
  <a href="https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases"><img src="https://img.shields.io/badge/Download-Releases-22C55E?style=flat-square" alt="Download" /></a>
  <a href="#license"><img src="https://img.shields.io/badge/License-MIT-3db89a?style=flat-square" alt="MIT License" /></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-1a212b?style=flat-square" alt="Windows" /></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python" /></a>
  <img src="https://img.shields.io/badge/UI-CustomTkinter-222b38?style=flat-square" alt="CustomTkinter" />
</p>

<p align="center">
  <b><a href="https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases">⬇ Download latest release</a></b>
</p>

<p align="center">
  <img src="assets/screenshot-credentials.png" alt="Schinza Credential Manager" width="860" />
</p>

---

## Download

Prebuilt Windows packages (onedir) are published on GitHub Releases:

**https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases**

1. Open the latest release (e.g. `schinza:1.8.6`)
2. Download the zip / asset and extract the **whole** `Schinza` folder
3. Run `Schinza.exe` (do not ship a lone `.exe` without `_internal/`)

Source repository: [Alexxxxxxxxxxxxy/schinza-wechat-certificate](https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate)

---

## Overview

**Schinza** is an open-source Windows desktop tool for local WeChat Official Account (公众号) ops:

| Module | What it does |
|--------|----------------|
| **Credential Manager** | Install bundled MITM CA, start local proxy, capture `__biz` / `uin` / `key` / `pass_ticket` from WeChat Desktop; **30‑minute TTL** with renew / copy JSON / **search by name** |
| **History Articles** | Fetch **7 / 30 / 90‑day / all / custom‑day** history; list export; per‑article or batch body export; optional **URL补录** |
| **List export** | JSON · CSV (Excel) · TSV · Markdown · plain links · title+link |
| **Article export** | Per-article or **batch**: **HTML** · **Markdown** · **TXT** · **JSON** · **Word (.docx)** |
| **Sync Server** | Import Schinza OA list CSV; match local valid credentials by name, then copy or batch upload (≤ 50/batch) to your own open API server |

All credentials and exports stay under local `data/`. The app never uploads automatically — only the **Sync Server** tab can upload matched credentials to the server address you fill in yourself (**no built-in default; you must enter it, e.g. `https://your-server.com/schinza`**).

---

## UI

Sidebar navigation (dark slate + green accent):

1. **Credential Manager** — CA install, proxy, add & capture, countdown cards  
2. **History Articles** — account · time range · fetch ·补录 · browse · export  
3. **Sync Server** — server URL (required) · import OA list CSV · match credentials · upload  

---

## Requirements

- Windows 10 / 11 (x64)
- WeChat **Desktop** (for credential capture)
- Python **3.11+** (development / build)
- For packaging: OpenSSL DLLs from your Python/conda env (`libssl` / `libcrypto`)

---

## Quick start (from source)

```powershell
git clone https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate.git
cd schinza-wechat-certificate

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: full mitmproxy CA (with private key) for capture/packaging
# Prefer: %USERPROFILE%\.mitmproxy\mitmproxy-ca.pem

python main.py
```

### First-time capture flow

1. **Credential Manager** → **Install CA** → restart WeChat Desktop  
2. Account name + any article URL → **Add & Capture**; or use **Batch Import** to load a CSV/TXT (column 1 = OA name, column 2 = article URL; comma/tab separated, header auto-detected)  
3. Open any article from that OA in WeChat Desktop  
4. Credentials appear (30‑minute TTL). **Renew** does not open a system browser — refresh the already-open article in WeChat; multi-OA traffic is routed by `__biz`  
5. **History Articles** → pick range (7 / 30 / 90 days, all, or custom days) → **Fetch** → export list or per-article body  

> Prefer **Add & Capture** over starting the proxy alone. Use **补录链接** when you need to add a missing article.

---

## Troubleshooting (fetch errors)

### "unknown error / unknownerror"
This is **WeChat server-side risk control** (`ret=-6, errmsg=unknownerror`), **not** a local
network/proxy issue: WeChat has flagged the account/session as abnormal and refuses to return
the article list.

- **First check** (network/proxy): Settings → Network & Internet → Proxy → turn off manual proxy,
  then restart the app. A reinstall often just clears leftover proxy state.
- **If network/proxy is fine and it still happens**: the account is rate-limited/flagged. Please:
  - Lower fetch frequency; avoid repeated "All" or bulk fetches across many accounts
  - Wait a while (hours to a day) and retry
  - If it persists, capture with a different WeChat account (avoid your main account)
- Since 1.7.4 the app shows the real reason (e.g. "微信风控拒绝" / "连接微信超时") instead of a bare unknown error.

### "连接微信超时 / 网络错误" (timeout / network error)
Direct connection to `mp.weixin.qq.com` failed: check your network, clear leftover proxy,
restart the app. The app already retries twice automatically.

### "Renew all" / renew does nothing
Renewal depends on WeChat emitting a request that carries **complete credentials**
(`__biz`+`uin`+`key` in the URL, e.g. getappmsgext / getmsg). Just refreshing an
already-open article page may not produce such a request. Please:

1. After starting renewal, **restart WeChat** (so the new proxy/CA takes effect)
2. **Re-open** the article (not just refresh an old tab), or **scroll the OA history
   page** to trigger getmsg
3. Still nothing? Check `data/capture_debug.log`:
   - "截获…凭证不完整" → traffic reaches the proxy but lacks `key`; scroll the history page
   - empty log → WeChat traffic isn't going through the proxy; restart WeChat and retry
   - "凭证已保存" → captured; wait for auto-apply

### "凭证已失效 / 会话异常" (expired / invalid session)
Credentials are valid for 30 minutes — re-capture / renew before fetching.

## Build Windows release

```powershell
.\build.ps1
```

```text
dist\Schinza\Schinza.exe
```

Distribute the **whole** `dist\Schinza` folder. Private CA material is required for a capture-capable binary — **never commit private keys**.

---

## Project layout

```text
├── assets/
├── app/
│   ├── ui.py                 # CustomTkinter UI
│   ├── mitm_capture.py       # In-process mitmproxy
│   ├── mitm_addon.py         # Creds + article sightings
│   ├── history_client.py     # getmsg + sighting merge
│   ├── history_ranges.py     # 7 / 30 / 90 / all / custom day presets
│   ├── history_export.py     # List export formats
│   ├── article_reader.py     # Article HTML / MD / TXT / JSON
│   ├── sightings.py          # Local补录 / MITM sightings store
│   ├── credentials.py
│   ├── store.py
│   └── ca_setup.py
├── tests/
├── main.py
├── build.ps1
├── requirements.txt
├── LICENSE
├── README.md
└── README.zh-CN.md
```

---

## Export formats

**History list:** JSON · CSV · TSV · Markdown · plain links · title+link  

**Single / batch article:** HTML · Markdown · TXT · JSON · Word (.docx)  

---

## Security & ethics

- Short-lived credentials in `data/accounts.json` only  
- History fetch bypasses the system MITM proxy (`trust_env=False`)  
- Use only on accounts/devices you are authorized to operate  
- Respect WeChat / Tencent terms and applicable laws  
- Do not publish private CA keys or live `uin` / `key` / `pass_ticket`  
- Authors are not responsible for misuse (see [Disclaimer](#disclaimer))

---

## Configuration notes

| Item | Detail |
|------|--------|
| Proxy | `127.0.0.1:8088` while capture is running |
| TTL | 30 minutes per credential |
| History window | 7 / 30 / 90 / all / custom days |
| Sync server URL | Required, no built-in default — fill in e.g. `https://your-server.com/schinza` |
| getmsg API | `https://mp.weixin.qq.com/mp/profile_ext?action=getmsg` |
| Releases | https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases |

---

## Development

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Contributions welcome via PR. Do not commit `data/*.json`, `dist/`, `.venv/`, or CA private keys.

---

## License

[MIT License](LICENSE) — Copyright (c) 2026 Schinza Contributors

---

## Disclaimer

Schinza is provided **solely as open-source software** for learning, research, and legitimate self-hosted use.

- By downloading, copying, modifying, or running this project, **you accept full responsibility** for your actions and consequences.
- Authors and contributors are **not liable** for loss, account bans, legal disputes, data leaks, or other damage from use or misuse.
- **Dangerous, abusive, illegal, or ToS-violating behavior by third parties has nothing to do with the authors.**
- Schinza is **not** affiliated with Tencent or WeChat.

**If you do not agree, do not use this software.**

---

<p align="center">
  <a href="https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases"><b>Download</b></a>
  ·
  <a href="./README.md"><b>English</b></a>
  ·
  <a href="./README.zh-CN.md">中文</a>
</p>
