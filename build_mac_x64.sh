#!/bin/bash
# build_mac_x64.sh — build an Intel (x86_64) Schinza.app/.dmg via Rosetta 2
# Usage: ./build_mac_x64.sh
# Requires: Rosetta 2 (arch -x86_64) + a universal2 (or x86_64) Python 3.11+
#   e.g. the official python.org macOS installer.
set -euo pipefail
cd "$(dirname "$0")"

echo "[*] 定位可在 x86_64 (Rosetta) 下运行的 Python 3.11+ ..."
PYX64=""
for p in /Library/Frameworks/Python.framework/Versions/*/bin/python3; do
  [ -x "$p" ] || continue
  if arch -x86_64 "$p" -c 'import sys; sys.exit(0)' 2>/dev/null; then
    PYX64="$p"
    break
  fi
done
if [ -z "$PYX64" ]; then
  echo "! 未找到支持 x86_64 (Rosetta) 的 Python 3.11+"
  echo "  请安装官方 universal2 安装包：https://www.python.org/downloads/macos/"
  exit 1
fi
echo "    - $PYX64"

VENV=".venv-mac-x64"
if [ ! -x "$VENV/bin/python" ]; then
  echo "[*] 创建 Rosetta x86_64 虚拟环境 ($VENV) ..."
  arch -x86_64 "$PYX64" -m venv "$VENV"
fi

# python.org Pythons ship without a CA bundle; point pip at certifi's cacert.pem
echo "[*] 配置 SSL 证书（复用 certifi CA 文件）..."
CERT_FILE="$("$VENV/bin/python" -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
if [ -z "$CERT_FILE" ] || [ ! -f "$CERT_FILE" ]; then
  CERT_FILE="$(".venv-mac/bin/python" -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
fi
if [ -n "$CERT_FILE" ] && [ -f "$CERT_FILE" ]; then
  export SSL_CERT_FILE="$CERT_FILE"
  echo "    - SSL_CERT_FILE=$CERT_FILE"
else
  echo "    ! 未找到 certifi CA，pip 可能因证书校验失败"
fi

arch -x86_64 "$VENV/bin/python" -m pip install -q --upgrade pip
arch -x86_64 "$VENV/bin/python" -m pip install -q -r requirements.txt

echo "[*] 准备 mitmproxy CA（从 ~/.mitmproxy 复制，打包必需）..."
MITM="$HOME/.mitmproxy"
if [ -d "$MITM" ]; then
  for f in mitmproxy-ca.pem mitmproxy-ca-cert.cer mitmproxy-ca-cert.p12 mitmproxy-ca.p12; do
    if [ -f "$MITM/$f" ]; then
      cp -f "$MITM/$f" "./$f"
      echo "    - $f"
    fi
  done
else
  echo "    ! 未找到 ~/.mitmproxy，请先运行一次: .venv-mac-x64/bin/mitmdump --version"
fi

if [ ! -f "assets/schinza.icns" ]; then
  echo "! 缺少 assets/schinza.icns，请先运行 ./build_mac.sh 生成"
  exit 1
fi

echo "[*] PyInstaller 打包 (x86_64) -> dist/Schinza.app ..."
arch -x86_64 "$VENV/bin/pyinstaller" --noconfirm Schinza-mac.spec

echo "[*] 重命名产物为 dist/Schinza-x64.app（避免覆盖 arm64 版）..."
rm -rf "dist/Schinza-x64.app" 2>/dev/null || true
mv "dist/Schinza.app" "dist/Schinza-x64.app"
echo "    - dist/Schinza-x64.app"

echo "[*] 生成 DMG -> dist/Schinza-mac-x64.dmg ..."
DMG_STAGE="build/dmg_stage_x64"
DMG_NAME="dist/Schinza-mac-x64.dmg"
rm -rf "$DMG_STAGE" 2>/dev/null || true
mkdir -p "$DMG_STAGE"
cp -R "dist/Schinza-x64.app" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"

if hdiutil create -volname "Schinza" -srcfolder "$DMG_STAGE" \
  -ov -format UDZO "$DMG_NAME" 2>&1 | tail -2; then
  rm -rf "$DMG_STAGE" 2>/dev/null || true
  echo "    - $DMG_NAME"
else
  echo "    ! DMG 生成失败（hdiutil 报错见上方），.app 产物不受影响"
  rm -rf "$DMG_STAGE" 2>/dev/null || true
fi

echo ""
echo "=========================================="
echo "✅ Intel (x86_64) 构建完成："
echo "   - dist/Schinza-x64.app"
echo "   - dist/Schinza-mac-x64.dmg"
echo "=========================================="
