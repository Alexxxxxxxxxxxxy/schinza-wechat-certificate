from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.updater import (  # noqa: E402
    APP_VERSION,
    _parse_version,
    is_newer_than,
)


def test_parse_version():
    assert _parse_version("Schinza-1.4.3") == (1, 4, 3)
    assert _parse_version("v2.0.1") == (2, 0, 1)
    assert _parse_version("1.10") == (1, 10)
    assert _parse_version("") == (0,)


def test_is_newer():
    assert is_newer_than("Schinza-1.7.0")
    assert is_newer_than("Schinza-1.4.4", current_version="1.4.3")
    assert not is_newer_than("Schinza-1.5.3")
    assert not is_newer_than("Schinza-1.5.2", current_version="1.5.3")
    assert not is_newer_than("Schinza-0.9.9", current_version="1.5.3")


def test_app_version_is_parseable():
    assert _parse_version(APP_VERSION) != (0,)
