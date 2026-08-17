<p align="center">
  <img src="assets/logo.png" alt="Schinza" width="128" height="128" />
</p>

<h1 align="center">Schinza</h1>

<p align="center">
  <a href="./README.md">English</a> · <a href="./README.zh-CN.md"><b>中文</b></a>
</p>

<p align="center">
  <strong>微信公众号凭证与历史文章 Windows / macOS 桌面助手</strong>
  <br />
  捕获短暂客户端密钥 · 管理 30 分钟有效期 · 拉取近 7 / 30 / 90 天 / 全部 / 自定义天数历史 · 列表与正文多格式导出（HTML / Markdown / TXT / JSON / Word）· 批量导入（CSV/TXT）· 批量导出
</p>

<p align="center">
  <a href="https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases"><img src="https://img.shields.io/badge/下载-Releases-22C55E?style=flat-square" alt="Download" /></a>
  <a href="#开源协议"><img src="https://img.shields.io/badge/License-MIT-3db89a?style=flat-square" alt="MIT License" /></a>
  <a href="#运行环境"><img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20%7C%20macOS%2012%2B-1a212b?style=flat-square" alt="Platform" /></a>
  <a href="#运行环境"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python" /></a>
  <img src="https://img.shields.io/badge/UI-CustomTkinter-222b38?style=flat-square" alt="CustomTkinter" />
</p>

<p align="center">
  <b><a href="https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases">⬇ 下载最新发行版</a></b>
</p>

<p align="center">
  <img src="assets/screenshot-credentials.png" alt="Schinza 凭证管理界面" width="860" />
</p>

---

## 下载

**Windows (x64)** 与 **macOS（Apple Silicon arm64）** 预编译包发布在 GitHub Releases：

**https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases**

| 平台 | 安装包 | 安装方式 |
|---|---|---|
| Windows x64 | `Schinza-windows-x64.zip` | 解压**整个** `Schinza` 文件夹，运行 `Schinza.exe`（保留 `_internal/`） |
| macOS · Apple 芯片 | `Schinza-mac-arm64.dmg` / `.zip` | 打开 DMG 把 `Schinza.app` 拖入 Applications；首次启动「右键 → 打开」（未签名） |

源码仓库：[Alexxxxxxxxxxxxy/schinza-wechat-certificate](https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate)

---

## 项目简介

**Schinza** 是一款开源 Windows / macOS 桌面工具，在本机完成公众号凭证与历史文章相关操作：

| 模块 | 功能 |
|------|------|
| **凭证管理** | 安装随包 MITM CA、启动本地代理，从微信桌面捕获 `__biz` / `uin` / `key` / `pass_ticket`；每套凭证 **30 分钟**有效，支持续约 / 复制 JSON / **按名称搜索** |
| **历史文章** | 拉取 **近 7 / 30 / 90 天 / 全部 / 自定义天数 / 自定义日期范围**历史；列表导出；单篇 / 批量正文导出；可选 **补录链接** |
| **列表导出** | JSON · CSV（Excel）· TSV · Markdown · 纯链接 · 标题+链接 |
| **正文导出** | 单篇或**批量**：**HTML** · **Markdown** · **TXT** · **JSON** · **CSV**（批量合并一个文件）· **Word (.docx)** |
| **同步服务器** | 导入 Schinza 公众号列表 CSV；本地凭证按名称匹配后一键复制或分批上传（≤50/批）到**你自己的**开放接口服务器 |

所有凭证与导出保存在本机 `data/`；应用不会自动上传，仅「同步服务器」页签会按你填写的服务器地址上传匹配到的凭证（**无内置默认地址，需自行填写**，如 `https://your-server.com/schinza`）。

---

## 贡献者

<a href="https://github.com/meichiny"><img src="https://avatars.githubusercontent.com/meichiny?s=80" width="48" height="48" alt="meichiny" title="meichiny" /></a>
<a href="https://github.com/Alexxxxxxxxxxxxy"><img src="https://avatars.githubusercontent.com/Alexxxxxxxxxxxxy?s=80" width="48" height="48" alt="Alexxxxxxxxxxxxy" title="Alexxxxxxxxxxxxy" /></a>

- [@meichiny](https://github.com/meichiny) — macOS 支持（跨平台代码、双架构打包、文档），见 [#4](https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/pull/4)
- [@Alexxxxxxxxxxxxy](https://github.com/Alexxxxxxxxxxxxy) — 项目作者与维护者

---

## 界面说明

左侧栏切换（深色 slate + 绿色强调）：

1. **凭证管理** — 安装 CA、代理、添加并抓包、倒计时卡片  
2. **历史文章** — 选择公众号 · 时间范围 · 拉取 · 补录 · 浏览 · 导出  
3. **同步服务器** — 服务器地址（必填）· 导入公众号列表 CSV · 匹配凭证 · 同步上传  

---

## 运行环境

- **Windows** 10 / 11（x64）
- **macOS** 12.0+（Monterey 及以上——微信 Mac 版要求 macOS 12+；程序自身二进制仅需 11.0 (arm64)）
- 微信**桌面版**（用于凭证捕获，Windows / macOS 均已实测；微信为 universal2 双架构安装包）
- Python **3.11+**（开发 / 打包）
- Windows 打包时需要 Python/conda 环境中的 OpenSSL DLL（`libssl` / `libcrypto`）；macOS 打包不需要额外 DLL

---

## 快速开始（源码）

**Windows：**

```powershell
git clone https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate.git
cd schinza-wechat-certificate

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 可选：复制完整 mitmproxy CA（含私钥）用于抓包/打包
# 推荐：%USERPROFILE%\.mitmproxy\mitmproxy-ca.pem

python main.py
```

**macOS：**

```bash
git clone https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate.git
cd schinza-wechat-certificate

python3 -m venv .venv-mac
.venv-mac/bin/pip install -r requirements.txt

# 可选：复制完整 mitmproxy CA（含私钥）用于抓包/打包
# 推荐：~/.mitmproxy/mitmproxy-ca.pem

.venv-mac/bin/python main.py
```

> macOS 上首次「安装 CA 证书」会调用 `security` 命令，可能弹出系统密码框（输入本机密码即可）；代理设置与恢复使用 `networksetup`（自动识别当前网络服务）。

### 首次抓包流程

1. **凭证管理** → **安装 CA 证书** → **重启微信桌面**  
2. 填写公众号名称 + 任意文章链接 → **添加并抓包**；或点 **批量导入**，选择 CSV/TXT（第一列公众号、第二列文章链接，逗号/Tab 分隔，自动识别表头）批量添加  
3. 在微信桌面打开该公众号任意一篇文章  
4. 卡片出现凭证（30 分钟）。过期后点 **续约**，在微信内刷新该号已打开文章（不弹系统浏览器）；多号同时打开时按 `__biz` 自动落到对应卡片  
5. **历史文章** → 选择 7 / 30 / 90 天 / 全部 / 自定义天数 → **拉取** → 导出列表或单篇正文  

> 请优先「添加并抓包」。需要补充文章时可用「补录链接」。

---

## 常见问题（拉取报错）

### 「unknown error / unknownerror」
这是**微信服务端风控返回**（`ret=-6, errmsg=unknownerror`），**不是**本地网络或代理问题：
账号/会话被微信识别为异常，拒绝返回文章列表。

- **先排查**（网络/代理）：打开 设置 → 网络和 Internet → 代理 → 手动设置代理 → 关闭，重启应用；
  重装能解决往往只是清掉了残留代理状态。
- **如果网络/代理正常仍出现**：说明是账号被风控。请：
  - 降低拉取频率，**不要**连续开「全部」或批量拉取多个公众号
  - 稍等一段时间再试（几小时到一天）
  - 仍持续出现 → 换一个微信账号重新抓包（避免用主力号）
- 1.7.4 起程序会显示具体原因（如「微信风控拒绝」「连接微信超时」），不再是无脑 unknown error。

### 「连接微信超时 / 网络错误」
直连 `mp.weixin.qq.com` 失败：检查网络、关闭残留代理、重启应用；程序已自动重试 2 次。

### 一键续约全部 / 续约没反应
续约依赖微信产生**带完整凭证**的请求（URL 里含 `__biz`+`uin`+`key`，如 getappmsgext / getmsg）。
只是刷新已打开的旧文章页可能不产生这类请求。请：

1. 点续约后，**先重启微信**（让新代理/证书生效）
2. **重新打开**该公众号文章（不要只刷新旧页面），或**滚动公众号历史消息页**触发 getmsg
3. 若仍没反应，查看 `data/capture_debug.log`：
   - 有「截获…凭证不完整」→ 流量到了代理但缺 key，请滚动历史消息页
   - 日志为空 → 微信流量没走代理，重启微信后再试
   - 有「凭证已保存」→ 已捕获，等待自动入库

### 「凭证已失效 / 会话异常」
凭证 30 分钟有效，过期后请重新抓包/续约。

## 打包 Windows 发行版

```powershell
.\build.ps1
```

```text
dist\Schinza\Schinza.exe
```

请分发**整个** `dist\Schinza` 文件夹。构建可抓包二进制需要带私钥的 CA — **切勿将私钥提交到公开仓库**。

## 打包 macOS 发行版

```bash
./build_mac.sh
```

```text
dist/Schinza.app
```

脚本会：创建 `.venv-mac` 虚拟环境 → 从 `~/.mitmproxy` 复制 CA → 用 `sips` + `iconutil` 生成 `.icns` 图标 → PyInstaller 打包为 `Schinza.app`，并额外生成 `dist/Schinza-mac-arm64.dmg`（UDZO 压缩格式，内含 Applications 快捷方式，双击挂载后拖入 Applications 即安装）。构建可抓包二进制需要带私钥的 CA — **切勿将私钥提交到公开仓库**。

> 当前打包产物为 **Apple Silicon (arm64)** 单架构。未签名 .app 在他人机器上首次打开需「右键 → 打开」绕过 Gatekeeper；正式分发建议使用 Apple Developer ID 签名 + 公证（Notarization）。

### macOS 常见问题
- **数据/日志位置**：macOS 打包版数据放在 `~/Library/Application Support/Schinza/data/`（`capture_debug.log`、`app.log` 在这里），不是 .app 包内。
- **浏览器报「连接不是私密连接」**：说明系统里信任的 CA 与当前版本不一致（更新版本会换新证书）。打开「钥匙串访问」→ 删除旧的 `mitmproxy` 证书 → 回程序点「安装 CA 证书」→ 重启微信/浏览器。程序会自动检测不一致并提示。
- **微信 Mac 抓不到凭证**：设置代理后**必须重启微信 Mac**（部分版本不跟随系统代理）。若重启后仍无流量，说明该微信版本绕过系统代理——自动抓包不可用，只能手动「粘贴凭证/补录链接」。
- **设置代理失败**：macOS 改代理需要管理员权限，失败时会提示手动设置：系统设置 → 网络 → 代理 → 网页代理/安全网页代理 `127.0.0.1:8088`。

### macOS 系统要求（.app / .dmg 产物）

- **Apple Silicon Mac**（M1 及更新）——CI 发布的安装包为 arm64 版
- **macOS 12.0 (Monterey)** 或更高版本——微信 Mac 4.x 要求 macOS 12+；程序自身二进制仅需 11.0 (arm64)
- 已安装**微信 Mac 版**（用于凭证捕获；微信为 universal2 双架构，两种芯片均可运行）
- 需要**管理员权限**的账号（安装信任根证书、设置系统代理时会弹出密码框）
- 建议 300MB 磁盘空间、2GB 以上可用内存

CI 暂不发布 Intel (x86_64) 版（Intel 的 `macos-13` runner 已退役）。本地可自行用 `./build_mac_x64.sh` 构建（基于 Rosetta 创建 x86_64 虚拟环境，需 Rosetta 2 与 python.org 的 universal2 Python）→ 产出 `dist/Schinza-x64.app` / `dist/Schinza-mac-x64.dmg`。

---

## 目录结构

```text
├── assets/
├── app/
│   ├── ui.py                 # CustomTkinter 界面
│   ├── mitm_capture.py       # 进程内 mitmproxy
│   ├── mitm_addon.py         # 凭证 + 文章目击
│   ├── history_client.py     # getmsg + 补录合并
│   ├── history_ranges.py     # 7 / 30 / 90 天 / 全部 / 自定义
│   ├── history_export.py     # 列表导出
│   ├── article_reader.py     # 正文 HTML / MD / TXT / JSON
│   ├── sightings.py          # 补录 / 抓包目击存储
│   ├── credentials.py
│   ├── store.py
│   └── ca_setup.py
├── tests/
├── main.py
├── build.ps1
├── build_mac.sh
├── Schinza.spec
├── Schinza-mac.spec
├── requirements.txt
├── LICENSE
├── README.md
└── README.zh-CN.md
```

---

## 导出格式

**历史列表：** JSON · CSV · TSV · Markdown · 纯链接 · 标题+链接  

**单篇 / 批量正文：** HTML · Markdown · TXT · JSON · CSV · Word (.docx)（CSV 批量 = 全部合并到一个文件）；文章内视频可自动下载（`视频/` 子目录）；**可选**抓取互动数据（阅读/在看/评论数，默认关）进入全部导出格式  

---

## 安全与使用规范

- 凭证短时有效，仅存本机 `data/accounts.json`  
- 历史拉取绕过系统 MITM 代理（`trust_env=False`）  
- 仅在您有权操作的账号与设备上使用  
- 遵守微信 / 腾讯服务条款及相关法律  
- 勿公开私有 CA 密钥或真实 `uin` / `key` / `pass_ticket`  
- 他人滥用与作者无关（见[免责声明](#免责声明)）

---

## 配置说明

| 项 | 说明 |
|----|------|
| 代理 | 抓包运行时为 `127.0.0.1:8088` |
| 有效期 | 每套凭证 30 分钟 |
| 历史窗口 | 近 7 / 30 / 90 天 / 全部 / 自定义天数 |
| 同步服务器地址 | 必填、无内置默认值，如 `https://your-server.com/schinza` |
| getmsg 接口 | `https://mp.weixin.qq.com/mp/profile_ext?action=getmsg` |
| 发行版下载 | https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases |

---

## 开发

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

欢迎 PR。请勿提交 `data/*.json`、`dist/`、`.venv/`、`.venv-mac/` 或 CA 私钥。

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

```text
Copyright (c) 2026 Schinza Contributors
```

---

## 免责声明

本项目**仅作为开源软件**提供，供学习、研究与合法自用参考。

- 下载、复制、修改或使用即视为已了解风险，并**自行承担全部责任与后果**。
- 作者及贡献者**不对**因使用或滥用导致的损失、封禁、纠纷、泄露等承担责任。
- **其他人实施的危险、滥用、违法或违规行为，与作者无关。**
- Schinza **与**腾讯或微信**无关联、背书或赞助关系**。

**若不同意以上声明，请勿使用本软件。**

---

<p align="center">
  <a href="https://github.com/Alexxxxxxxxxxxxy/schinza-wechat-certificate/releases"><b>下载</b></a>
  ·
  <a href="./README.md">English</a>
  ·
  <a href="./README.zh-CN.md"><b>中文</b></a>
</p>
