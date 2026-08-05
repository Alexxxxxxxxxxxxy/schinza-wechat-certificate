# Schinza 凭证助手（Windows · 内置 MITM）

本地「抄钥匙」工具：内置 mitmproxy 抓包 + 30 分钟凭证管理 + 复制 JSON。  

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
