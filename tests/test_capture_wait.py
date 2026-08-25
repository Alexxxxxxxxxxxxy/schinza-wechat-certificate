"""Single-account capture stall hint (Mac hang looked like a spinner)."""

from __future__ import annotations

import unittest

from app.capture_wait import should_show_capture_stall_hint


class CaptureStallHintTests(unittest.TestCase):
    def test_not_before_20s(self) -> None:
        self.assertFalse(should_show_capture_stall_hint(19.9, waiting=True, already_shown=False))

    def test_after_20s_while_waiting(self) -> None:
        self.assertTrue(should_show_capture_stall_hint(20.0, waiting=True, already_shown=False))

    def test_not_when_already_shown(self) -> None:
        self.assertFalse(should_show_capture_stall_hint(30.0, waiting=True, already_shown=True))

    def test_not_when_not_waiting(self) -> None:
        self.assertFalse(should_show_capture_stall_hint(30.0, waiting=False, already_shown=False))


if __name__ == "__main__":
    unittest.main()
