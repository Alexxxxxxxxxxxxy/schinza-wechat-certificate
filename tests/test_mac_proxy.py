"""macOS system-proxy helpers: service discovery and bypass sanitization."""

from __future__ import annotations

import unittest

from app.mac_proxy import (
    parse_network_services,
    parse_route_interface,
    parse_service_for_device,
    sanitize_mac_proxy_bypass,
    start_message_warns_proxy_failed,
)


class ParseRouteInterfaceTests(unittest.TestCase):
    def test_reads_en0(self) -> None:
        out = "   route to: default\ninterface: en0\n    flags: <UP,GATEWAY>\n"
        self.assertEqual(parse_route_interface(out), "en0")

    def test_utun_has_no_hardware_port(self) -> None:
        self.assertEqual(parse_route_interface("interface: utun4\n"), "utun4")


class ParseServiceForDeviceTests(unittest.TestCase):
    HP = (
        "Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: aa:bb\n\n"
        "Hardware Port: Thunderbolt Bridge\nDevice: en1\nEthernet Address: cc:dd\n"
    )

    def test_maps_en0_to_wifi(self) -> None:
        self.assertEqual(parse_service_for_device(self.HP, "en0"), "Wi-Fi")

    def test_utun_returns_none(self) -> None:
        self.assertIsNone(parse_service_for_device(self.HP, "utun4"))


class ParseNetworkServicesTests(unittest.TestCase):
    def test_skips_header_and_disabled(self) -> None:
        out = (
            "An asterisk (*) denotes that a network service is disabled.\n"
            "Wi-Fi\n"
            "* Thunderbolt Bridge\n"
            "USB 10/100/1000 LAN\n"
        )
        self.assertEqual(
            parse_network_services(out),
            ["Wi-Fi", "USB 10/100/1000 LAN"],
        )


class SanitizeBypassTests(unittest.TestCase):
    def test_drops_weixin_and_qq_bypass(self) -> None:
        cleaned = sanitize_mac_proxy_bypass(
            ["*.local", "*.qq.com", "*.weixin.qq.com", "127.0.0.1"]
        )
        self.assertIn("*.local", cleaned)
        self.assertIn("127.0.0.1", cleaned)
        self.assertNotIn("*.qq.com", cleaned)
        self.assertNotIn("*.weixin.qq.com", cleaned)

    def test_keeps_localhost_even_if_missing(self) -> None:
        cleaned = sanitize_mac_proxy_bypass([])
        self.assertIn("127.0.0.1", cleaned)
        self.assertIn("localhost", cleaned)


class StartMessageTests(unittest.TestCase):
    def test_detects_proxy_setup_failure(self) -> None:
        msg = "抓包代理已启动 127.0.0.1:8088。\n代理已启动，但系统代理设置失败：无法识别当前网络服务"
        self.assertTrue(start_message_warns_proxy_failed(msg))

    def test_success_is_not_a_warning(self) -> None:
        msg = "抓包代理已启动 127.0.0.1:8088。\n已设置系统代理（Wi-Fi）→ 127.0.0.1:8088。"
        self.assertFalse(start_message_warns_proxy_failed(msg))


if __name__ == "__main__":
    unittest.main()
