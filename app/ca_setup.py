"""Prepare bundled mitmproxy CA and install into Windows trust store."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Public trust install (may be cert-only). Proxy signing needs PEM with private key.
P12_PUBLIC = "mitmproxy-ca-cert.p12"
P12_FULL = "mitmproxy-ca.p12"
PEM_CA = "mitmproxy-ca.pem"
CER_NAME = "mitmproxy-ca-cert.cer"

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8088


def resource_roots(app_root: Path) -> list[Path]:
    roots = [app_root]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    # Developer machine fallback
    home_mitm = Path.home() / ".mitmproxy"
    if home_mitm.is_dir():
        roots.append(home_mitm)
    return roots


def _find(app_root: Path, name: str) -> Path | None:
    for root in resource_roots(app_root):
        p = root / name
        if p.is_file():
            return p
    return None


def ensure_beside(app_root: Path, name: str) -> Path | None:
    dest = app_root / name
    if dest.is_file():
        return dest
    src = _find(app_root, name)
    if src is None:
        return None
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest if dest.is_file() else None


def confdir(app_root: Path) -> Path:
    d = app_root / "data" / "mitm_conf"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _export_cer_from_p12(p12_path: Path, cer_path: Path) -> bool:
    from cryptography.hazmat.primitives.serialization import Encoding, pkcs12

    data = p12_path.read_bytes()
    for pwd in (b"", b"mitmproxy", None):
        try:
            key, cert, extra = pkcs12.load_key_and_certificates(data, pwd)
        except Exception:
            continue
        chosen = cert
        if chosen is None and extra:
            chosen = extra[0]
        if chosen is None:
            continue
        cer_path.write_bytes(chosen.public_bytes(Encoding.DER))
        return True
    # load_pkcs12 additional_certs path
    try:
        from cryptography.hazmat.primitives.serialization.pkcs12 import load_pkcs12

        for pwd in (b"", None):
            try:
                obj = load_pkcs12(data, pwd)
            except Exception:
                continue
            c = obj.cert.certificate if obj.cert else None
            if c is None and obj.additional_certs:
                c = obj.additional_certs[0].certificate
            if c is not None:
                cer_path.write_bytes(c.public_bytes(Encoding.DER))
                return True
    except Exception:
        pass
    return False


def prepare_mitm_confdir(app_root: Path) -> tuple[Path, str]:
    """
    Ensure mitmproxy confdir has mitmproxy-ca.pem (cert+key).
    Prefer bundled PEM / full p12; fall back to ~/.mitmproxy.
    """
    cdir = confdir(app_root)
    dest_pem = cdir / "mitmproxy-ca.pem"

    # 1) Already prepared
    if dest_pem.is_file() and dest_pem.stat().st_size > 100:
        ensure_beside(app_root, CER_NAME)
        return cdir, f"已使用代理证书目录：{cdir}"

    # 2) Bundled / adjacent PEM (has private key)
    pem = ensure_beside(app_root, PEM_CA) or _find(app_root, PEM_CA)
    if pem is not None:
        shutil.copy2(pem, dest_pem)
        # derive .cer for install UI
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives.serialization import Encoding

            text = pem.read_text(encoding="utf-8")
            # take first cert block
            begin = text.find("-----BEGIN CERTIFICATE-----")
            end = text.find("-----END CERTIFICATE-----")
            if begin >= 0 and end > begin:
                block = text[begin : end + len("-----END CERTIFICATE-----")]
                cert = x509.load_pem_x509_certificate(block.encode())
                (app_root / CER_NAME).write_bytes(cert.public_bytes(Encoding.DER))
        except Exception:
            pass
        return cdir, f"已从 {pem.name} 准备代理 CA → {cdir}"

    # 3) Full p12 with private key (mitmproxy-ca.p12)
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        pkcs12,
    )

    for name in (P12_FULL, P12_PUBLIC):
        p12 = ensure_beside(app_root, name) or _find(app_root, name)
        if p12 is None:
            continue
        data = p12.read_bytes()
        for pwd in (b"", b"mitmproxy", None):
            try:
                key, cert, extra = pkcs12.load_key_and_certificates(data, pwd)
            except Exception:
                continue
            if key is None or cert is None:
                continue
            pem_bytes = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
            pem_bytes += cert.public_bytes(Encoding.PEM)
            dest_pem.write_bytes(pem_bytes)
            (app_root / CER_NAME).write_bytes(cert.public_bytes(Encoding.DER))
            return cdir, f"已从 {p12.name} 提取代理 CA → {cdir}"

    # 4) Public-only p12 cannot sign — explain clearly
    pub = ensure_beside(app_root, P12_PUBLIC) or _find(app_root, P12_PUBLIC)
    if pub is not None:
        _export_cer_from_p12(pub, app_root / CER_NAME)
        raise RuntimeError(
            f"{P12_PUBLIC} 只有公钥、没有私钥，无法启动抓包代理。\n"
            f"请把本机完整 CA 一并放入程序目录后重试：\n"
            f"  - {PEM_CA}  （推荐，来自 %USERPROFILE%\\.mitmproxy\\）\n"
            f"  - 或 {P12_FULL}\n"
            f"当前也可先点「安装 CA 证书」导入公钥；但代理必须用带私钥的 PEM。"
        )

    raise FileNotFoundError(
        f"未找到代理 CA。请将 {PEM_CA} 或 {P12_FULL} 放到：{app_root}"
    )


def install_ca_windows(app_root: Path) -> tuple[bool, str]:
    """Import public CA into Current User Root store via certutil."""
    cer = app_root / CER_NAME
    if not cer.is_file():
        # try export from public p12 or prepare confdir (which writes cer)
        pub = ensure_beside(app_root, P12_PUBLIC) or _find(app_root, P12_PUBLIC)
        if pub and _export_cer_from_p12(pub, cer):
            pass
        else:
            try:
                prepare_mitm_confdir(app_root)
            except Exception:
                pass
        cer = ensure_beside(app_root, CER_NAME) or (app_root / CER_NAME)

    if not cer.is_file():
        p12 = ensure_beside(app_root, P12_PUBLIC) or _find(app_root, P12_PUBLIC)
        if p12 is None:
            return False, f"未找到 {CER_NAME} / {P12_PUBLIC}"
        cmd = [
            "certutil",
            "-user",
            "-p",
            "",
            "-importPFX",
            "Root",
            str(p12),
            "NoExport",
        ]
    else:
        cmd = ["certutil", "-user", "-addstore", "Root", str(cer)]

    try:
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        return False, "找不到 certutil，请手动双击安装 mitmproxy-ca-cert.cer"

    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode == 0 or "已经存在" in out or "already in store" in out.lower() or "成功" in out:
        return True, "已将 CA 导入「当前用户 → 受信任的根证书颁发机构」。请重启微信桌面后再抓包。"
    return False, out or f"certutil 退出码 {proc.returncode}"


def open_p12_in_explorer(app_root: Path) -> tuple[bool, str]:
    for name in (P12_PUBLIC, P12_FULL, CER_NAME, PEM_CA):
        p = ensure_beside(app_root, name) or _find(app_root, name)
        if p is not None:
            try:
                subprocess.Popen(["explorer", "/select,", str(p)])
                return True, f"已在资源管理器中定位：{p}"
            except Exception as exc:  # noqa: BLE001
                return False, str(exc)
    return False, "未找到证书文件"
