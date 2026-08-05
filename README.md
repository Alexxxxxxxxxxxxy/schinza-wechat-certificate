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
  Capture short-lived MP client keys · Manage 30‑minute TTL · Fetch last‑7‑day articles · Export in multiple formats
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/License-MIT-3db89a?style=flat-square" alt="MIT License" /></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-1a212b?style=flat-square" alt="Windows" /></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python" /></a>
  <img src="https://img.shields.io/badge/UI-CustomTkinter-222b38?style=flat-square" alt="CustomTkinter" />
</p>

---

## Overview

**Schinza** is an open-source Windows desktop tool that helps operators work with WeChat Official Accounts (公众号) locally:

| Module | What it does |
|--------|----------------|
| **Credential Manager** | Install a bundled MITM CA, start a local proxy, capture `__biz` / `uin` / `key` / `pass_ticket` from WeChat Desktop, keep each account key for **30 minutes** with renew / copy JSON |
| **History Articles** | Pick an **unexpired** account and pull the last **7 days** of articles via the same `profile_ext?action=getmsg` flow used by Schinza server tooling |
| **Export** | JSON · CSV (Excel) · TSV · Markdown · plain links · title+link text — copy to clipboard or save to disk |

All credentials and exports stay on the machine under `data/`. Nothing is uploaded by this app.

---

## Screenshots / UI

The app uses a dual-tab layout:

1. **Credential Manager** — CA install, proxy, add account & capture, account cards with countdown  
2. **History Articles** — select active credential → fetch → browse / export  

Window and executable icons use the Schinza mark in `assets/`.

---

## Requirements

- Windows 10 / 11 (x64)
- WeChat **Desktop** (for credential capture)
- Python **3.11+** (development / build)
- For packaging: OpenSSL DLLs from your Python/conda env (`libssl` / `libcrypto`)

---

## Quick start (from source)

```powershell
git clone https://github.com/<your-org>/Schinza.git
cd Schinza

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: copy a full mitmproxy CA (includes private key) for packaging/capture
# Prefer: %USERPROFILE%\.mitmproxy\mitmproxy-ca.pem

python main.py
```

### First-time capture flow

1. Open **Credential Manager** → **Install CA** → restart WeChat Desktop  
2. Enter account name + any article URL of that OA → **Add & Capture**  
3. In WeChat Desktop, open any article from that account  
4. Credentials appear on the card (30‑minute TTL). Use **Renew** when expired  
5. Switch to **History Articles**, select the account → **Fetch last 7 days** → export as needed  

> Tip: Prefer **Add & Capture** over starting the proxy alone. Binding an account first avoids orphan captures.

---

## Build Windows release

```powershell
.\build.ps1
```

Output (onedir — distribute the **whole folder**):

```text
dist\Schinza\Schinza.exe
```

Do **not** ship a lone `.exe` without `_internal/` and the OpenSSL DLLs next to it.

Private CA material (`mitmproxy-ca.pem` with key) is required to build a capture-capable binary. **Never commit private keys** to a public repository.

---

## Project layout

```text
Schinza/
├── assets/                 # Brand logo & Windows icon
├── app/
│   ├── ui.py               # CustomTkinter UI (tabs, cards, export)
│   ├── mitm_capture.py     # In-process mitmproxy + system proxy
│   ├── mitm_addon.py       # Credential capture addon
│   ├── history_client.py   # getmsg history client
│   ├── history_export.py   # Multi-format export
│   ├── credentials.py      # Parse / validate credential blobs
│   ├── store.py            # Local accounts.json (30 min TTL)
│   └── ca_setup.py         # Prepare / install CA
├── tests/
├── main.py
├── build.ps1
├── requirements.txt
├── LICENSE
├── README.md               # English (this file)
└── README.zh-CN.md         # 中文文档
```

---

## Export formats

| Format | Use case |
|--------|----------|
| JSON | Full structured payload |
| CSV (Excel) | Spreadsheet / Excel (UTF-8 BOM) |
| TSV | Tab-separated pipelines |
| Markdown | Docs / notes |
| Plain links TXT | Link-only lists |
| Title + link TXT | Human-readable lists |

---

## Security & ethics

- Credentials are **short-lived** and stored only in `data/accounts.json` on disk.  
- History requests **bypass the system MITM proxy** (`trust_env=False`) and talk to WeChat directly.  
- Use only on accounts and devices you are **authorized** to operate.  
- Respect WeChat / Tencent terms of service and applicable laws.  
- Do not publish private CA keys, live `uin`/`key`/`pass_ticket`, or production secrets.  
- This project is provided for legitimate operations tooling and research; authors are not responsible for misuse.

---

## Configuration notes

| Item | Detail |
|------|--------|
| Proxy | `127.0.0.1:8088` when capture is running |
| TTL | 30 minutes per credential (`app/store.py`) |
| History window | Last 7 days (`HISTORY_DAYS` in `app/ui.py`) |
| getmsg API | `https://mp.weixin.qq.com/mp/profile_ext?action=getmsg` |

---

## Development

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py

# Lightweight checks
python -c "import tests.test_credentials as t; t.test_parse_url(); print('ok')"
```

Contributions are welcome via pull requests. Please keep changes focused, avoid committing `data/*.json`, `dist/`, `.venv/`, or CA private keys.

---

## License

This project is released under the [MIT License](LICENSE).

```text
Copyright (c) 2026 Schinza Contributors
```

---

## Disclaimer

Schinza is an independent open-source project. It is **not** affiliated with, endorsed by, or sponsored by Tencent or WeChat. “WeChat” and “微信” are trademarks of their respective owners.

---

<p align="center">
  <a href="./README.md"><b>English</b></a> · <a href="./README.zh-CN.md">中文</a>
</p>
