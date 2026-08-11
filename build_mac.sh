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

echo "[*] 生成 DMG 镜像 -> dist/Schinza-mac-arm64.dmg ..."
DMG_STAGE="build/dmg_stage"
DMG_NAME="dist/Schinza-mac-arm64.dmg"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"
cp -R "dist/Schinza.app" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"

if hdiutil create -volname "Schinza" -srcfolder "$DMG_STAGE" \
  -ov -format UDZO "$DMG_NAME" 2>&1 | tail -3; then
  rm -rf "$DMG_STAGE"
  echo "    - $DMG_NAME"
else
  echo "    ! DMG 生成失败（hdiutil 报错见上方），.app 产物不受影响"
  rm -rf "$DMG_STAGE"
fi

echo ""
echo "=========================================="
echo "✅ 完成："
echo "   - dist/Schinza.app"
echo "   - dist/Schinza-mac-arm64.dmg（可分发，双击挂载后拖入 Applications）"
echo "=========================================="
