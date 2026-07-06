#!/usr/bin/env python3
"""Autotests for mac layout shortcut daemon."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

ABC = "com.apple.keylayout.ABC"
RUSSIAN = "com.apple.keylayout.Russian"

CG_FLAG_CONTROL = 1 << 18
CG_FLAG_SHIFT = 1 << 17
VK_1 = 0x12
VK_2 = 0x13


def make_event(keycode: int, flags: int, hid: bool = True) -> MagicMock:
    event = MagicMock()

    def get_flags(_event):
        return flags

    def get_keycode(_event, field):
        if field == "kCGKeyboardEventKeycode":
            return keycode
        if field == "kCGEventSourceStateID":
            return 1 if hid else 0
        raise KeyError(field)

    event.get_flags = get_flags
    event.get_keycode = get_keycode
    return event


class TestMacLayoutShortcutDaemon(unittest.TestCase):
    def _make_daemon(self, consume: bool = False):
        from zmk_mac_layout_daemon import MacLayoutShortcutDaemon

        config = {
            "shortcut_layouts": {"1": ABC, "2": RUSSIAN},
            "hid_events_only": True,
            "consume_shortcuts": consume,
            "debounce_ms": 50,
        }
        with patch("zmk_mac_layout_daemon.warm_input_source_cache"):
            return MacLayoutShortcutDaemon(config)

    def test_ctrl_shift_1_switches_abc(self):
        from zmk_mac_layout_daemon import kCGKeyboardEventKeycode

        daemon = self._make_daemon()
        event = MagicMock()
        with patch("zmk_mac_layout_daemon.CGEventGetFlags", return_value=CG_FLAG_CONTROL | CG_FLAG_SHIFT):
            with patch("zmk_mac_layout_daemon.CGEventGetIntegerValueField") as get_field:
                with patch("zmk_mac_layout_daemon.is_hid_keyboard_event", return_value=True):
                    with patch("zmk_mac_layout_daemon.current_input_source_id", return_value=RUSSIAN):
                        with patch("zmk_mac_layout_daemon.switch_macime_layout", return_value=True) as switch:
                            get_field.side_effect = lambda _e, field: VK_1 if field == kCGKeyboardEventKeycode else 0
                            result = daemon.handle_key_down(event)
        switch.assert_called_once_with("/usr/local/bin/macime", ABC)
        self.assertIs(result, event)

    def test_ctrl_shift_2_switches_russian(self):
        from zmk_mac_layout_daemon import kCGKeyboardEventKeycode

        daemon = self._make_daemon()
        event = MagicMock()
        with patch("zmk_mac_layout_daemon.CGEventGetFlags", return_value=CG_FLAG_CONTROL | CG_FLAG_SHIFT):
            with patch("zmk_mac_layout_daemon.CGEventGetIntegerValueField") as get_field:
                with patch("zmk_mac_layout_daemon.is_hid_keyboard_event", return_value=True):
                    with patch("zmk_mac_layout_daemon.current_input_source_id", return_value=ABC):
                        with patch("zmk_mac_layout_daemon.switch_macime_layout", return_value=True) as switch:
                            get_field.side_effect = lambda _e, field: VK_2 if field == kCGKeyboardEventKeycode else 0
                            daemon.handle_key_down(event)
        switch.assert_called_once_with("/usr/local/bin/macime", RUSSIAN)

    def test_skips_non_hid_when_configured(self):
        daemon = self._make_daemon()
        event = MagicMock()
        with patch("zmk_mac_layout_daemon.is_hid_keyboard_event", return_value=False):
            with patch("zmk_mac_layout_daemon.switch_macime_layout") as switch:
                result = daemon.handle_key_down(event)
        switch.assert_not_called()
        self.assertIs(result, event)

    def test_debounce_duplicate(self):
        daemon = self._make_daemon()
        daemon._last_switch_at = time.monotonic()
        daemon._last_layout_id = ABC
        event = MagicMock()
        with patch("zmk_mac_layout_daemon.CGEventGetFlags", return_value=CG_FLAG_CONTROL | CG_FLAG_SHIFT):
            with patch("zmk_mac_layout_daemon.CGEventGetIntegerValueField", return_value=VK_1):
                with patch("zmk_mac_layout_daemon.is_hid_keyboard_event", return_value=True):
                    with patch("zmk_mac_layout_daemon.switch_macime_layout") as switch:
                        daemon.handle_key_down(event)
        switch.assert_not_called()

    def test_consume_shortcuts_default_enabled(self):
        from zmk_mac_layout_daemon import MacLayoutShortcutDaemon

        with patch("zmk_mac_layout_daemon.warm_input_source_cache"):
            daemon = MacLayoutShortcutDaemon(
                {
                    "shortcut_layouts": {"1": ABC, "2": RUSSIAN},
                    "consume_shortcuts": True,
                }
            )
        self.assertTrue(daemon.consume_shortcuts)

    def test_consume_shortcuts(self):
        daemon = self._make_daemon(consume=True)
        event = MagicMock()
        with patch("zmk_mac_layout_daemon.CGEventGetFlags", return_value=CG_FLAG_CONTROL | CG_FLAG_SHIFT):
            with patch("zmk_mac_layout_daemon.CGEventGetIntegerValueField", return_value=VK_1):
                with patch("zmk_mac_layout_daemon.is_hid_keyboard_event", return_value=True):
                    with patch("zmk_mac_layout_daemon.current_input_source_id", return_value=RUSSIAN):
                        with patch("zmk_mac_layout_daemon.switch_macime_layout", return_value=True):
                            result = daemon.handle_key_down(event)
        self.assertIsNone(result)


class TestZmkTis(unittest.TestCase):
    def test_layout_for_shortcut(self):
        from zmk_mac_layout_daemon import layout_for_shortcut

        layouts = {"1": ABC, "2": RUSSIAN}
        self.assertEqual(layout_for_shortcut(layouts, "1"), ABC)
        self.assertEqual(layout_for_shortcut(layouts, "2"), RUSSIAN)
        self.assertIsNone(layout_for_shortcut(layouts, "3"))


if __name__ == "__main__":
    unittest.main()
