<p align="center">
  <img src="assets/logo.png" alt="Schinza" width="128" height="128" />
</p>

<h1 align="center">Schinza</h1>

<p align="center">
  <a href="./README.md">English</a> · <a href="./README.zh-CN.md"><b>中文</b></a>
</p>

<p align="center">
  <strong>微信公众号凭证与历史文章 Windows 桌面助手</strong>
  <br />
  捕获短暂客户端密钥 · 管理 30 分钟有效期 · 拉取近 7 天文章 · 多格式导出
</p>

<p align="center">
  <a href="#开源协议"><img src="https://img.shields.io/badge/License-MIT-3db89a?style=flat-square" alt="MIT License" /></a>
  <a href="#运行环境"><img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-1a212b?style=flat-square" alt="Windows" /></a>
  <a href="#运行环境"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python" /></a>
  <img src="https://img.shields.io/badge/UI-CustomTkinter-222b38?style=flat-square" alt="CustomTkinter" />
</p>

---

## 项目简介

**Schinza** 是一款开源的 Windows 桌面工具，帮助运营人员在本机处理微信公众号相关能力：

| 模块 | 功能 |
|------|------|
| **凭证管理** | 安装随包 MITM CA、启动本地代理，从微信桌面捕获 `__biz` / `uin` / `key` / `pass_ticket`，每套凭证保留 **30 分钟**，支持续约 / 复制 JSON |
| **历史文章** | 选择**未过期**的公众号凭证，通过与 Schinza 服务端相同的 `profile_ext?action=getmsg` 流程拉取近 **7 天**文章 |
| **导出** | JSON · CSV（Excel）· TSV · Markdown · 纯链接 · 标题+链接 — 可复制到剪贴板或保存为文件 |

所有凭证与导出结果仅保存在本机 `data/`，应用本身不会上传任何数据。

---

## 界面说明

应用采用顶部双栏切换：

1. **凭证管理** — 安装 CA、代理、添加并抓包、账号卡片与倒计时  
2. **历史文章** — 选择有效凭证 → 拉取 → 浏览 / 导出  

窗口图标与可执行文件图标见 `assets/`。

---

## 运行环境

- Windows 10 / 11（x64）
- 微信**桌面版**（用于凭证捕获）
- Python **3.11+**（开发 / 打包）
- 打包时需要 Python/conda 环境中的 OpenSSL DLL（`libssl` / `libcrypto`）

---

## 快速开始（源码）

```powershell
git clone https://github.com/<your-org>/Schinza.git
cd Schinza

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 可选：复制完整 mitmproxy CA（含私钥）用于抓包/打包
# 推荐来源：%USERPROFILE%\.mitmproxy\mitmproxy-ca.pem

python main.py
```

### 首次抓包流程

1. 打开 **凭证管理** → **安装 CA 证书** → **重启微信桌面**  
2. 填写公众号名称 + 该号任意一篇文章链接 → **添加并抓包**  
3. 在微信桌面中打开该公众号任意一篇文章  
4. 卡片上出现凭证（30 分钟有效）。过期后点 **续约**  
5. 切换到 **历史文章**，选择该号 → **拉取近7天** → 按需导出  

> 提示：请优先使用「添加并抓包」，不要只开代理就去打开文章，以免抓到未绑定公众号的孤儿凭证。

---

## 打包 Windows 发行版

```powershell
.\build.ps1
```

输出（onedir — 请分发**整个文件夹**）：

```text
dist\Schinza\Schinza.exe
```

请勿只拷贝单个 `.exe`（缺少 `_internal/` 与旁路 OpenSSL DLL 将无法运行）。

构建可抓包的二进制需要带私钥的 CA（`mitmproxy-ca.pem`）。**切勿将私钥提交到公开仓库。**

---

## 目录结构

```text
Schinza/
├── assets/                 # 品牌 Logo 与 Windows 图标
├── app/
│   ├── ui.py               # CustomTkinter 界面
│   ├── mitm_capture.py     # 进程内 mitmproxy + 系统代理
│   ├── mitm_addon.py       # 凭证捕获插件
│   ├── history_client.py   # getmsg 历史拉取
│   ├── history_export.py   # 多格式导出
│   ├── credentials.py      # 凭证解析 / 校验
│   ├── store.py            # 本地 accounts.json（30 分钟 TTL）
│   └── ca_setup.py         # CA 准备与安装
├── tests/
├── main.py
├── build.ps1
├── requirements.txt
├── LICENSE
├── README.md               # English docs
└── README.zh-CN.md         # 中文文档（本文件）
```

---

## 导出格式

| 格式 | 适用场景 |
|------|----------|
| JSON | 完整结构化数据 |
| CSV（Excel） | 表格 / Excel（含 UTF-8 BOM） |
| TSV | 制表符分隔流水线 |
| Markdown | 文档 / 笔记 |
| 纯链接 TXT | 仅链接列表 |
| 标题+链接 TXT | 可读列表 |

---

## 安全与使用规范

- 凭证为**短时有效**，仅保存在本机 `data/accounts.json`。  
- 历史拉取会**绕过系统 MITM 代理**（`trust_env=False`），直连微信。  
- 仅在您**有权操作**的账号与设备上使用。  
- 请遵守微信 / 腾讯服务条款及相关法律法规。  
- 不要公开私有 CA 密钥，以及真实的 `uin` / `key` / `pass_ticket` 等生产密钥。  
- 本项目面向合法运营与研究场景；作者不对滥用行为负责。

---

## 配置说明

| 项 | 说明 |
|----|------|
| 代理 | 抓包运行时为 `127.0.0.1:8088` |
| 有效期 | 每套凭证 30 分钟（`app/store.py`） |
| 历史窗口 | 近 7 天（`app/ui.py` 中 `HISTORY_DAYS`） |
| getmsg 接口 | `https://mp.weixin.qq.com/mp/profile_ext?action=getmsg` |

---

## 开发

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py

# 轻量自检
python -c "import tests.test_credentials as t; t.test_parse_url(); print('ok')"
```

欢迎通过 Pull Request 贡献代码。请保持改动聚焦，勿提交 `data/*.json`、`dist/`、`.venv/` 或 CA 私钥。

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

```text
Copyright (c) 2026 Schinza Contributors
```

---

## 免责声明

Schinza 为独立开源项目，**与**腾讯或微信**无任何关联、背书或赞助关系**。「WeChat」「微信」为其各自权利人的商标。

---

<p align="center">
  <a href="./README.md">English</a> · <a href="./README.zh-CN.md"><b>中文</b></a>
</p>
