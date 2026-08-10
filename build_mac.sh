#!/bin/bash
# build_mac.sh — build Schinza as a double-clickable macOS .app
# Usage: ./build_mac.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "[*] 准备 Python 虚拟环境 (.venv-mac) ..."
if [ ! -x ".venv-mac/bin/python" ]; then
  python3 -m venv .venv-mac
fi
.venv-mac/bin/pip install -q --upgrade pip
.venv-mac/bin/pip install -q -r requirements.txt

echo "[*] 准备 mitmproxy CA（从 ~/.mitmproxy 复制，打包必需）..."
MITM="$HOME/.mitmproxy"
if [ -d "$MITM" ]; then
  for f in mitmproxy-ca.pem mitmproxy-ca-cert.cer mitmproxy-ca-cert.p12 mitmproxy-ca.p12; do
    if [ -f "$MITM/$f" ]; then
      cp -f "$MITM/$f" "./$f"
      echo "    - $f"
    else
      echo "    ! 缺少 $f（首次运行 mitmdump 会自动生成）"
    fi
  done
else
  echo "    ! 未找到 ~/.mitmproxy，请先运行一次: .venv-mac/bin/mitmdump --version"
fi

echo "[*] 生成 assets/schinza.icns ..."
SRC="assets/logo-256.png"
if [ -f assets/logo-512.png ]; then SRC="assets/logo-512.png"; fi
if [ -f assets/logo-1024.png ]; then SRC="assets/logo-1024.png"; fi
ICONSET="build/icon.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for spec in "16:icon_16x16.png" "32:icon_16x16@2x.png" "32:icon_32x32.png" \
            "64:icon_32x32@2x.png" "128:icon_128x128.png" "256:icon_128x128@2x.png" \
            "256:icon_256x256.png" "512:icon_256x256@2x.png" "512:icon_512x512.png" \
            "1024:icon_512x512@2x.png"; do
  size="${spec%%:*}"
  name="${spec##*:}"
  sips -z "$size" "$size" "$SRC" --out "$ICONSET/$name" >/dev/null
done
iconutil -c icns "$ICONSET" -o "assets/schinza.icns"
echo "    - assets/schinza.icns"

echo "[*] PyInstaller 打包 -> dist/Schinza.app ..."
.venv-mac/bin/pyinstaller --noconfirm Schinza-mac.spec

echo ""
echo "=========================================="
echo "✅ 完成：dist/Schinza.app"
echo "   双击即可运行；或执行: open dist/Schinza.app"
echo "=========================================="
