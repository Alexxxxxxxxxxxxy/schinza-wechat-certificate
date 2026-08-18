"""CA fingerprint helpers for macOS trust consistency."""

from __future__ import annotations

from app.ca_setup import _parse_sha1_fingerprint


def test_parse_security_sha1_hash() -> None:
    out = "SHA-1 hash: AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD\n"
    assert _parse_sha1_fingerprint(out) == "aabbccddeeff00112233445566778899aabbccdd"


def test_parse_openssl_fingerprint() -> None:
    out = "sha1 Fingerprint=12:34:56:78:9A:BC:DE:F0:11:22:33:44:55:66:77:88:99:AA:BB:CC\n"
    assert _parse_sha1_fingerprint(out) == "123456789abcdef0112233445566778899aabbcc"


def test_parse_no_match() -> None:
    assert _parse_sha1_fingerprint("nothing here") is None
    assert _parse_sha1_fingerprint("") is None
