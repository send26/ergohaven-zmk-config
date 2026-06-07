#!/usr/bin/env python3
"""Sync macOS keyboard layout with OP36 en/ru layers over Raw HID."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import hid
import objc
from AppKit import NSDate, NSDefaultRunLoopMode, NSRunLoop
from Foundation import NSDistributedNotificationCenter, NSObject
from Quartz import TISCopyCurrentKeyboardInputSource, kTISPropertyInputSourceID

RAW_HID_USAGE_PAGE = 0xFF60
RAW_HID_USAGE = 0x61
HID_CMD_LAYOUT = 0xAC
REPORT_SIZE = 32

DEFAULT_CONFIG = Path(__file__).with_name("layout_sync.json")
INPUT_SOURCE_NOTIFICATIONS = (
    "com.apple.inputmethodKit.IMKClient.currentInputSourceDidChange",
    "com.apple.system.config.keyboard.layoutchanged",
)


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


def current_input_source_id() -> str | None:
    source = TISCopyCurrentKeyboardInputSource()
    if source is None:
        return None

    source_id = source.get(kTISPropertyInputSourceID)
    if source_id is None:
        return None

    return str(source_id)


def layout_index_for_source(source_id: str, layouts: list[str]) -> int | None:
    try:
        return layouts.index(source_id)
    except ValueError:
        return None


def find_raw_hid_device() -> hid.Device | None:
    for device_info in hid.enumerate():
        if (
            device_info.get("usage_page") == RAW_HID_USAGE_PAGE
            and device_info.get("usage") == RAW_HID_USAGE
        ):
            return hid.Device(path=device_info["path"])
    return None


def send_layout_report(device: hid.Device, layout_index: int) -> None:
    payload = [HID_CMD_LAYOUT, layout_index] + [0x00] * (REPORT_SIZE - 2)
    report = bytes([0x00] + payload)
    device.write(report)


class LayoutSync:
    def __init__(self, config: dict) -> None:
        self.layouts: list[str] = config["layouts"]
        self.poll_interval_ms: int = config.get("poll_interval_ms", 500)
        self.reconnect_delay_ms: int = config.get("reconnect_delay_ms", 3000)
        self.device: hid.Device | None = None
        self.last_source_id: str | None = None
        self.last_sent_index: int | None = None

    def close_device(self) -> None:
        if self.device is not None:
            try:
                self.device.close()
            except OSError:
                pass
            self.device = None

    def ensure_device(self) -> bool:
        if self.device is not None:
            return True

        self.device = find_raw_hid_device()
        if self.device is None:
            return False

        manufacturer = self.device.manufacturer or "unknown"
        product = self.device.product or "unknown"
        logging.info("Connected to Raw HID device: %s %s", manufacturer, product)
        return True

    def sync_current_layout(self) -> None:
        source_id = current_input_source_id()
        if source_id is None:
            logging.warning("Unable to read current input source")
            return

        if source_id != self.last_source_id:
            logging.info("Input source: %s", source_id)
            self.last_source_id = source_id

        layout_index = layout_index_for_source(source_id, self.layouts)
        if layout_index is None:
            logging.debug("Input source %s is not mapped in config", source_id)
            return

        if layout_index == self.last_sent_index:
            return

        if not self.ensure_device():
            logging.warning("Raw HID device not found, will retry")
            return

        try:
            send_layout_report(self.device, layout_index)
        except OSError as error:
            logging.error("Failed to send layout report: %s", error)
            self.close_device()
            return

        layer_name = "en" if layout_index == 0 else "ru"
        logging.info("Sent layer sync: %s (index %d)", layer_name, layout_index)
        self.last_sent_index = layout_index

    def run_once(self) -> None:
        if not self.ensure_device():
            logging.error("Raw HID device not found")
            return
        self.sync_current_layout()

    def run_forever(self) -> None:
        observer = InputSourceObserver.alloc().initWithCallback_(self.sync_current_layout)

        notification_center = NSDistributedNotificationCenter.defaultCenter()
        for notification_name in INPUT_SOURCE_NOTIFICATIONS:
            notification_center.addObserver_selector_name_object_(
                observer,
                "inputSourceChanged:",
                notification_name,
                None,
            )

        logging.info("Watching input source changes. Mapped layouts: %s", self.layouts)
        logging.info("Current input source: %s", current_input_source_id())

        poll_interval = self.poll_interval_ms / 1000.0
        reconnect_interval = self.reconnect_delay_ms / 1000.0
        next_reconnect_at = datetime.min

        while True:
            self.sync_current_layout()

            if self.device is None and datetime.now() >= next_reconnect_at:
                self.ensure_device()
                next_reconnect_at = datetime.now() + timedelta(seconds=reconnect_interval)

            until = NSDate.dateWithTimeIntervalSinceNow_(poll_interval)
            NSRunLoop.currentRunLoop().runMode_beforeDate_(NSDefaultRunLoopMode, until)


class InputSourceObserver(NSObject):
    def initWithCallback_(self, callback):
        self = objc.super(InputSourceObserver, self).init()
        if self is None:
            return None
        self.callback = callback
        return self

    def inputSourceChanged_(self, _notification) -> None:
        if self.callback is not None:
            self.callback()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to layout_sync.json",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Sync once and exit",
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
        logging.error("Config file not found: %s", args.config)
        return 1

    config = load_config(args.config)
    sync = LayoutSync(config)

    if args.once:
        sync.run_once()
        sync.close_device()
        return 0

    try:
        sync.run_forever()
    except KeyboardInterrupt:
        logging.info("Stopped")
    finally:
        sync.close_device()

    return 0


if __name__ == "__main__":
    sys.exit(main())
