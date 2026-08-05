# Schinza 凭证助手（Windows · 内置 MITM）

本地「抄钥匙」工具：内置 mitmproxy 抓包 + 30 分钟凭证管理 + 复制 JSON。  
UI：CustomTkinter（墨色青绿）。

## 发给别人怎么用

1. 确认目录里有完整 CA（从本机 `%USERPROFILE%\.mitmproxy\` 复制）：
   - **`mitmproxy-ca.pem`**（含私钥，抓包必须）
   - `mitmproxy-ca-cert.p12` / `.cer`（给对方安装信任）
2. 运行 `.\build.ps1` 得到 `dist\SchinzaCertificate\` **整个目录**（含 exe 与 libssl DLL）
3. 打成 zip 发给对方：整个 `SchinzaCertificate` 文件夹 + `mitmproxy-ca.pem` + 证书文件
4. 对方首次：
   - 打开助手 → **安装 CA 证书** → **重启微信桌面**
   - 填写公众号名称 + 文章链接 → **添加并抓包**（自动启代理 `127.0.0.1:8088`）
   - **再**用微信桌面打开该公众号任意一篇文章 → 凭证自动入库（30 分钟）
   - 不要只点「手动启停代理」就去开文章（未绑定公众号时不会入库）
5. 到期点 **续约**；有效期内 **复制凭证** 粘到 Schinza 服务器

注意：仅有 `mitmproxy-ca-cert.p12`（公钥）不够启动代理；必须带上 `mitmproxy-ca.pem`。

## 谁需要 MITM？

| 角色 | 需要？ |
|------|--------|
| 抓凭证的电脑（本助手） | **要**（内置代理 + 安装随包 CA） |
| Schinza 服务器 | **不要**（只用已保存的钥匙调 getmsg） |

随包 CA（`mitmproxy-ca-cert.p12`）用于开箱一致；**不要**再让对方各自生成另一套 CA，否则和代理对不上。

## 开发运行

```powershell
cd certificate
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# 确认 mitmproxy-ca-cert.p12 在本目录
python main.py
```

## 安全说明

- 凭证只存本机 `data\accounts.json`
- 分发的 p12 含抓包用 CA，仅限你们内部使用；勿公开发布
