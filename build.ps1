# Build Schinza (onedir) — conda OpenSSL DLLs must be next to exe
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
  python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt

if (-not (Test-Path "mitmproxy-ca.pem")) {
  Write-Error "Missing mitmproxy-ca.pem (with private key). Copy from %USERPROFILE%\.mitmproxy\"
}
if (-not (Test-Path "assets\schinza.ico")) {
  Write-Error "Missing assets\schinza.ico"
}

# Discover conda OpenSSL DLLs used by this Python
$dllLines = & python -c @"
import sys
from pathlib import Path
base = Path(sys.base_prefix)
for folder in (base / 'Library' / 'bin', base / 'DLLs', base / 'bin'):
    if not folder.is_dir():
        continue
    for pat in ('libssl*.dll', 'libcrypto*.dll'):
        for hit in folder.glob(pat):
            print(hit)
"@
$binArgs = @()
foreach ($dll in $dllLines) {
  $dll = "$dll".Trim()
  if ($dll -and (Test-Path $dll)) {
    $binArgs += @("--add-binary", "$dll;.")
    Write-Host "Bundle DLL: $dll"
  }
}

$argsList = @(
  "--noconfirm", "--clean",
  "--windowed",
  "--onedir",
  "--name", "Schinza",
  "--icon", "assets\schinza.ico",
  "--paths", ".",
  "--additional-hooks-dir", "hooks",
  "--collect-all", "customtkinter",
  "--collect-all", "mitmproxy",
  "--collect-all", "cryptography",
  "--collect-all", "aioquic",
  "--hidden-import", "ssl",
  "--hidden-import", "_ssl",
  "--hidden-import", "pyperclip",
  "--hidden-import", "requests",
  "--hidden-import", "app.mitm_addon",
  "--hidden-import", "app.history_client",
  "--hidden-import", "app.history_export",
  "--hidden-import", "app.article_reader",
  "--hidden-import", "app.sightings",
  "--hidden-import", "app.history_ranges",
  "--hidden-import", "bs4",
  "--hidden-import", "lxml",
  "--add-data", "mitmproxy-ca.pem;.",
  "--add-data", "app\mitm_addon.py;app",
  "--add-data", "assets\schinza.ico;assets",
  "--add-data", "assets\logo.png;assets",
  "--add-data", "assets\logo-128.png;assets",
  "--add-data", "assets\logo-256.png;assets"
) + $binArgs

if (Test-Path "mitmproxy-ca-cert.p12") { $argsList += @("--add-data", "mitmproxy-ca-cert.p12;.") }
if (Test-Path "mitmproxy-ca.p12") { $argsList += @("--add-data", "mitmproxy-ca.p12;.") }
if (Test-Path "mitmproxy-ca-cert.cer") { $argsList += @("--add-data", "mitmproxy-ca-cert.cer;.") }

$argsList += @("main.py")

# Remove stale artifacts that confuse users
Remove-Item -Force "dist\Schinza.exe","dist\SchinzaCertificate.exe" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "dist\SchinzaCertificate" -ErrorAction SilentlyContinue

$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& python -m PyInstaller @argsList
$pyExit = $LASTEXITCODE
$ErrorActionPreference = $prev
if ($pyExit -ne 0) {
  Write-Error "PyInstaller failed with exit code $pyExit"
}

$outDir = "dist\Schinza"
Copy-Item -Force "mitmproxy-ca.pem" "$outDir\" -ErrorAction SilentlyContinue
Copy-Item -Force "mitmproxy-ca-cert.p12" "$outDir\" -ErrorAction SilentlyContinue
Copy-Item -Force "mitmproxy-ca-cert.cer" "$outDir\" -ErrorAction SilentlyContinue
Copy-Item -Force "mitmproxy-ca.p12" "$outDir\" -ErrorAction SilentlyContinue

# Also drop OpenSSL DLLs next to exe (belt and suspenders)
foreach ($dll in $dllLines) {
  $dll = "$dll".Trim()
  if ($dll -and (Test-Path $dll)) {
    Copy-Item -Force $dll "$outDir\"
  }
}

Write-Host ""
Write-Host "Done: $PSScriptRoot\$outDir\Schinza.exe"
Write-Host "Zip the whole folder dist\Schinza for distribution."
