#!/usr/bin/env python3
"""Listen for Ctrl+Shift+1/2 from the keyboard and switch macOS input source."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    kCGEventKeyDown,
    kCGEventSourceStateHIDSystemState,
    kCGEventSourceStateID,
    kCGEventTapOptionDefault,
    kCGHeadInsertEventTap,
    kCGHIDEventTap,
    kCGKeyboardEventKeycode,
    kCFRunLoopCommonModes,
)

from zmk_tis import (
    DEFAULT_MACIME_PATH,
    current_input_source_id,
    switch_macime_layout,
    warm_input_source_cache,
)

DEFAULT_CONFIG = Path(__file__).with_name("mac_layout.json")

# macOS virtual keycodes (ANSI)
VK_1 = 0x12
VK_2 = 0x13

CG_FLAG_CONTROL = 1 << 18
CG_FLAG_SHIFT = 1 << 17


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


def layout_for_shortcut(shortcut_layouts: dict[str, str], digit: str) -> str | None:
    return shortcut_layouts.get(digit) or shortcut_layouts.get(str(digit))


def is_hid_keyboard_event(event) -> bool:
    source_state = CGEventGetIntegerValueField(event, kCGEventSourceStateID)
    return source_state == kCGEventSourceStateHIDSystemState


def modifier_mask_matches(flags: int) -> bool:
    return (flags & CG_FLAG_CONTROL) and (flags & CG_FLAG_SHIFT)


class MacLayoutShortcutDaemon:
    def __init__(self, config: dict) -> None:
        raw_layouts = config.get("shortcut_layouts", {})
        self.shortcut_layouts: dict[str, str] = {
            str(key): value for key, value in raw_layouts.items()
        }
        self.macime_path: str = config.get("macime_path", DEFAULT_MACIME_PATH)
        self.hid_events_only: bool = bool(config.get("hid_events_only", True))
        self.consume_shortcuts: bool = bool(config.get("consume_shortcuts", False))
        self.debounce_sec: float = config.get("debounce_ms", 120) / 1000.0
        self._last_switch_at: float = 0.0
        self._last_layout_id: str | None = None
        warm_input_source_cache(set(self.shortcut_layouts.values()))

    def handle_key_down(self, event) -> object | None:
        if self.hid_events_only and not is_hid_keyboard_event(event):
            return event

        flags = CGEventGetFlags(event)
        if not modifier_mask_matches(flags):
            return event

        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
        digit: str | None = None
        if keycode == VK_1:
            digit = "1"
        elif keycode == VK_2:
            digit = "2"
        else:
            return event

        layout_id = layout_for_shortcut(self.shortcut_layouts, digit)
        if layout_id is None:
            return event

        now = time.monotonic()
        if (
            now - self._last_switch_at < self.debounce_sec
            and layout_id == self._last_layout_id
        ):
            logging.debug("Debounced duplicate shortcut for %s", layout_id)
            return None if self.consume_shortcuts else event

        if current_input_source_id() == layout_id:
            logging.debug("Already on %s", layout_id)
            self._last_switch_at = now
            self._last_layout_id = layout_id
            return None if self.consume_shortcuts else event

        if switch_macime_layout(self.macime_path, layout_id):
            self._last_switch_at = now
            self._last_layout_id = layout_id
            logging.info("Shortcut Ctrl+Shift+%s → %s", digit, layout_id)

        return None if self.consume_shortcuts else event

    def run_forever(self) -> None:
        def callback(proxy, event_type, event, refcon):  # noqa: ARG001
            if event_type != kCGEventKeyDown:
                return event
            try:
                return self.handle_key_down(event)
            except Exception:
                logging.exception("Shortcut handler failed")
                return event

        mask = CGEventMaskBit(kCGEventKeyDown)
        tap = CGEventTapCreate(
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            mask,
            callback,
            None,
        )
        if tap is None:
            raise RuntimeError(
                "Failed to create event tap. Grant Accessibility to Terminal/Cursor "
                "in System Settings → Privacy & Security → Accessibility."
            )

        run_loop_source = CFMachPortCreateRunLoopSource(None, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), run_loop_source, kCFRunLoopCommonModes)
        CGEventTapEnable(tap, True)

        logging.info(
            "Listening for Ctrl+Shift+1/2 → %s",
            self.shortcut_layouts,
        )
        CFRunLoopRun()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to mac_layout.json",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.config.exists():
        logging.error("Config not found: %s", args.config)
        return 1

    daemon = MacLayoutShortcutDaemon(load_config(args.config))
    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        logging.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
