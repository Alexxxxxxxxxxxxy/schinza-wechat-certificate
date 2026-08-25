"""macOS system-proxy helpers (pure parse/sanitize + networksetup wrappers)."""

from __future__ import annotations

import subprocess
from typing import Any

from app.ca_setup import PROXY_HOST, PROXY_PORT

_DROP_BYPASS = ("qq.com", "weixin", "wechat", "tencent.com")
_LOCAL_BYPASS = ("127.0.0.1", "localhost", "::1")


def parse_route_interface(route_out: str) -> str | None:
    for line in (route_out or "").splitlines():
        line = line.strip()
        if line.lower().startswith("interface:"):
            dev = line.split(":", 1)[1].strip()
            return dev or None
    return None


def parse_service_for_device(hardware_ports: str, device: str) -> str | None:
    if not device:
        return None
    cur: str | None = None
    for line in (hardware_ports or "").splitlines():
        line = line.strip()
        if line.startswith("Hardware Port:"):
            cur = line.split(":", 1)[1].strip()
        elif line.startswith("Device:") and line.split(":", 1)[1].strip() == device:
            return cur
    return None


def parse_network_services(list_out: str) -> list[str]:
    services: list[str] = []
    for line in (list_out or "").splitlines():
        line = line.strip()
        if not line or line.startswith("An asterisk"):
            continue
        if line.startswith("*"):
            continue
        services.append(line)
    return services


def sanitize_mac_proxy_bypass(domains: list[str]) -> list[str]:
    kept: list[str] = []
    seen: set[str] = set()
    for raw in domains:
        d = str(raw or "").strip()
        if not d:
            continue
        low = d.lower()
        if any(marker in low for marker in _DROP_BYPASS):
            continue
        key = low
        if key in seen:
            continue
        seen.add(key)
        kept.append(d)
    for must in _LOCAL_BYPASS:
        if must.lower() not in seen:
            kept.append(must)
            seen.add(must.lower())
    if "*.local" not in seen and "*.local" not in {x.lower() for x in kept}:
        kept.append("*.local")
    return kept


def start_message_warns_proxy_failed(msg: str) -> bool:
    text = msg or ""
    return "系统代理设置失败" in text or "无法识别当前网络服务" in text


def mac_default_service() -> str | None:
    try:
        route = subprocess.check_output(["route", "-n", "get", "default"], text=True)
    except Exception:
        return None
    dev = parse_route_interface(route)
    if not dev:
        return None
    try:
        hp = subprocess.check_output(
            ["networksetup", "-listallhardwareports"], text=True
        )
    except Exception:
        return None
    return parse_service_for_device(hp, dev)


def mac_list_services() -> list[str]:
    try:
        out = subprocess.check_output(
            ["networksetup", "-listallnetworkservices"], text=True
        )
    except Exception:
        return []
    return parse_network_services(out)


def _read_proxy(svc: str, kind: str) -> dict[str, object]:
    cmd = f"-get{'securewebproxy' if kind == 'secure' else 'webproxy'}"
    try:
        out = subprocess.check_output(["networksetup", cmd, svc], text=True)
    except Exception:
        return {"enabled": False}
    state: dict[str, object] = {"enabled": False}
    for line in out.splitlines():
        k, _, v = line.partition(":")
        k = k.strip().lower()
        v = v.strip()
        if k == "enabled":
            state["enabled"] = v.lower() in ("yes", "true", "1")
        elif k == "server":
            state["server"] = v
        elif k == "port":
            try:
                state["port"] = int(v)
            except ValueError:
                pass
    return state


def _read_bypass(svc: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["networksetup", "-getproxybypassdomains", svc], text=True
        )
    except Exception:
        return []
    domains: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("there aren't any"):
            continue
        domains.append(line)
    return domains


def _run_networksetup(args: list[str]) -> None:
    subprocess.run(
        ["networksetup", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def apply_mac_system_proxy(
    backup: dict[str, dict[str, Any]] | None,
) -> tuple[bool, str, dict[str, dict[str, Any]] | None]:
    """Turn on HTTP+HTTPS proxy for every enabled service; strip WeChat bypasses."""
    services = mac_list_services()
    default = mac_default_service()
    if default and default not in services:
        services.insert(0, default)
    if not services:
        return False, "无法识别当前网络服务，请手动设置系统代理 127.0.0.1:8088", backup

    if backup is None:
        backup = {}
        for svc in services:
            backup[svc] = {
                "web": _read_proxy(svc, "web"),
                "secure": _read_proxy(svc, "secure"),
                "bypass": _read_bypass(svc),
            }

    ok_names: list[str] = []
    errors: list[str] = []
    for svc in services:
        try:
            _run_networksetup(["-setwebproxy", svc, PROXY_HOST, str(PROXY_PORT)])
            _run_networksetup(["-setsecurewebproxy", svc, PROXY_HOST, str(PROXY_PORT)])
            _run_networksetup(["-setwebproxystate", svc, "on"])
            _run_networksetup(["-setsecurewebproxystate", svc, "on"])
            prev = (backup.get(svc) or {}).get("bypass") or []
            cleaned = sanitize_mac_proxy_bypass(list(prev) if isinstance(prev, list) else [])
            _run_networksetup(["-setproxybypassdomains", svc, *cleaned])
            ok_names.append(svc)
        except subprocess.CalledProcessError as exc:
            errors.append(f"{svc}: {exc.stderr or exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{svc}: {exc}")

    if not ok_names:
        detail = errors[0] if errors else "networksetup 失败"
        return (
            False,
            "设置 macOS 系统代理需要管理员权限，networksetup 执行失败："
            f"{detail}\n"
            "可手动设置：系统设置 → 网络 → 详细信息 → 代理 → 勾选网页代理/安全网页代理，"
            "服务器 127.0.0.1 端口 8088，然后重启微信。"
            "若开了 Clash/Surge TUN，请先关闭增强模式。",
            backup,
        )

    names = "、".join(ok_names)
    extra = f"（部分网卡失败：{errors[0]}）" if errors else ""
    return (
        True,
        f"已设置系统代理（{names}）→ 127.0.0.1:8088。"
        "请重启微信 Mac（部分版本不会自动跟随系统代理）再打开文章抓包。"
        "若开了 Clash/Surge TUN，请先关闭增强模式。"
        + extra,
        backup,
    )


def restore_mac_system_proxy(
    backup: dict[str, dict[str, Any]] | None,
) -> tuple[bool, str]:
    services = list(backup.keys()) if backup else mac_list_services()
    if not services:
        return True, "无需恢复系统代理"
    try:
        for svc in services:
            st = (backup or {}).get(svc) or {}
            web = st.get("web") or {}
            secure = st.get("secure") or {}
            if web.get("server"):
                _run_networksetup(
                    [
                        "-setwebproxy",
                        svc,
                        str(web["server"]),
                        str(web.get("port") or 80),
                    ]
                )
            _run_networksetup(
                ["-setwebproxystate", svc, "on" if web.get("enabled") else "off"]
            )
            if secure.get("server"):
                _run_networksetup(
                    [
                        "-setsecurewebproxy",
                        svc,
                        str(secure["server"]),
                        str(secure.get("port") or 80),
                    ]
                )
            _run_networksetup(
                [
                    "-setsecurewebproxystate",
                    svc,
                    "on" if secure.get("enabled") else "off",
                ]
            )
            bypass = st.get("bypass")
            if isinstance(bypass, list) and bypass:
                _run_networksetup(["-setproxybypassdomains", svc, *bypass])
            elif bypass == [] or bypass is None:
                # leave sanitized list if we never captured a previous one
                pass
        return True, "已恢复系统代理设置（macOS）"
    except subprocess.CalledProcessError as exc:
        return (
            False,
            "恢复 macOS 系统代理失败："
            f"{exc.stderr or exc}",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"恢复系统代理异常：{exc}"
