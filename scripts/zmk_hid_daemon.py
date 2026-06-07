#!/usr/bin/env python3
"""ZMK Raw HID daemon: Mac layout sync + keyboard layer reporting for SketchyBar."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import hid
import objc
from AppKit import NSDate, NSDefaultRunLoopMode, NSRunLoop
from Foundation import NSBundle, NSDistributedNotificationCenter, NSObject

RAW_HID_USAGE_PAGE = 0xFF60
RAW_HID_USAGE = 0x61
HID_CMD_LAYOUT = 0xAC
HID_CMD_LAYER = 0xAD
REPORT_SIZE = 32

DEFAULT_LAYOUT_CONFIG = Path(__file__).with_name("layout_sync.json")
DEFAULT_LAYERS_CONFIG = Path(__file__).with_name("layers.json")
DEFAULT_STATE_DIR = Path.home() / ".cache" / "zmk_layer"
DEFAULT_STATE_FILE = DEFAULT_STATE_DIR / "state.json"

INPUT_SOURCE_NOTIFICATIONS = (
    "com.apple.inputmethodKit.IMKClient.currentInputSourceDidChange",
    "com.apple.system.config.keyboard.layoutchanged",
)


def _load_tis_api_ctypes() -> dict:
    import ctypes
    import ctypes.util

    carbon_path = ctypes.util.find_library("Carbon")
    if carbon_path is None:
        raise RuntimeError("Carbon framework not found")

    carbon = ctypes.cdll.LoadLibrary(carbon_path)
    objc_bridge = ctypes.PyDLL(objc._objc.__file__)
    objc_bridge.PyObjCObject_New.restype = ctypes.py_object
    objc_bridge.PyObjCObject_New.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

    def objcify(ptr: int | None):
        if not ptr:
            return None
        return objc_bridge.PyObjCObject_New(ptr, 0, 1)

    carbon.TISCopyCurrentKeyboardInputSource.restype = ctypes.c_void_p
    carbon.TISCopyCurrentKeyboardInputSource.argtypes = []

    carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
    carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    input_source_id_key = ctypes.c_void_p.in_dll(carbon, "kTISPropertyInputSourceID")

    def copy_current_keyboard_input_source():
        return objcify(carbon.TISCopyCurrentKeyboardInputSource())

    def get_input_source_property(source, _property_key):
        if source is None:
            return None
        return objcify(
            carbon.TISGetInputSourceProperty(
                source.__c_void_p__(),
                input_source_id_key,
            )
        )

    return {
        "TISCopyCurrentKeyboardInputSource": copy_current_keyboard_input_source,
        "TISGetInputSourceProperty": get_input_source_property,
        "kTISPropertyInputSourceID": input_source_id_key,
    }


def _load_tis_api() -> dict:
    try:
        from HIToolbox import (
            TISCopyCurrentKeyboardInputSource,
            TISGetInputSourceProperty,
            kTISPropertyInputSourceID,
        )

        return {
            "TISCopyCurrentKeyboardInputSource": TISCopyCurrentKeyboardInputSource,
            "TISGetInputSourceProperty": TISGetInputSourceProperty,
            "kTISPropertyInputSourceID": kTISPropertyInputSourceID,
        }
    except ImportError:
        pass

    bundle = NSBundle.bundleWithIdentifier_("com.apple.HIToolbox")
    if bundle is not None:
        api: dict = {}
        try:
            objc.loadBundleFunctions(
                bundle,
                api,
                [
                    ("TISCopyCurrentKeyboardInputSource", b"@"),
                    ("TISGetInputSourceProperty", b"@@@"),
                ],
            )
            objc.loadBundleVariables(
                bundle,
                api,
                [("kTISPropertyInputSourceID", b"@")],
            )
            return api
        except TypeError:
            pass

    return _load_tis_api_ctypes()


_TIS = _load_tis_api()


def load_json_config(path: Path) -> dict | list:
    with path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


def current_input_source_id() -> str | None:
    source = _TIS["TISCopyCurrentKeyboardInputSource"]()
    if source is None:
        return None

    source_id = _TIS["TISGetInputSourceProperty"](
        source,
        _TIS["kTISPropertyInputSourceID"],
    )
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


def write_layer_state(state_file: Path, layer_index: int, layers_config: list[dict]) -> None:
    layer_meta = next((layer for layer in layers_config if layer["index"] == layer_index), None)
    state = {
        "layer": layer_index,
        "id": layer_meta["id"] if layer_meta else f"layer_{layer_index}",
        "label": layer_meta["label"] if layer_meta else f"L{layer_index}",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state) + "\n", encoding="utf-8")


def trigger_sketchybar_update() -> None:
    try:
        subprocess.run(
            ["sketchybar", "--trigger", "zmk_layer_update"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        logging.debug("SketchyBar trigger failed: %s", error)


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


class ZmkHidDaemon:
    def __init__(
        self,
        layout_config: dict,
        layers_config: list[dict],
        state_file: Path,
        read_layers: bool = True,
        sync_layout: bool = True,
    ) -> None:
        self.layouts: list[str] = layout_config.get("layouts", [])
        self.poll_interval_ms: int = layout_config.get("poll_interval_ms", 500)
        self.reconnect_delay_ms: int = layout_config.get("reconnect_delay_ms", 3000)
        self.layers_config = layers_config
        self.state_file = state_file
        self.read_layers = read_layers
        self.sync_layout = sync_layout

        self.device: hid.Device | None = None
        self.device_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.read_thread: threading.Thread | None = None

        self.last_source_id: str | None = None
        self.last_sent_index: int | None = None
        self.last_layer_index: int | None = None

    def close_device(self) -> None:
        with self.device_lock:
            if self.device is not None:
                try:
                    self.device.close()
                except OSError:
                    pass
                self.device = None

    def ensure_device(self) -> bool:
        with self.device_lock:
            if self.device is not None:
                return True

            self.device = find_raw_hid_device()
            if self.device is None:
                return False

            try:
                self.device.nonblocking = True
            except AttributeError:
                pass

            manufacturer = self.device.manufacturer or "unknown"
            product = self.device.product or "unknown"
            logging.info("Connected to Raw HID device: %s %s", manufacturer, product)
            return True

    def start_reader(self) -> None:
        if not self.read_layers or self.read_thread is not None:
            return

        self.read_thread = threading.Thread(target=self._read_loop, name="zmk-hid-reader", daemon=True)
        self.read_thread.start()

    def _read_loop(self) -> None:
        while not self.stop_event.is_set():
            device = None
            with self.device_lock:
                device = self.device

            if device is None:
                time.sleep(self.reconnect_delay_ms / 1000.0)
                continue

            try:
                data = device.read(REPORT_SIZE, timeout_ms=500)
            except OSError as error:
                logging.error("Failed to read Raw HID report: %s", error)
                self.close_device()
                time.sleep(self.reconnect_delay_ms / 1000.0)
                continue

            if not data:
                continue

            self._handle_report(bytes(data))

    def _handle_report(self, report: bytes) -> None:
        if len(report) < 2:
            return

        command = report[0]
        if command != HID_CMD_LAYER:
            logging.debug("Ignoring Raw HID report command 0x%02x", command)
            return

        layer_index = report[1]
        if layer_index == self.last_layer_index:
            return

        layer_meta = next(
            (layer for layer in self.layers_config if layer["index"] == layer_index),
            None,
        )
        layer_label = layer_meta["label"] if layer_meta else f"L{layer_index}"

        self.last_layer_index = layer_index
        write_layer_state(self.state_file, layer_index, self.layers_config)
        logging.info("Layer update: %s (index %d)", layer_label, layer_index)
        trigger_sketchybar_update()

    def sync_current_layout(self) -> None:
        if not self.sync_layout or not self.layouts:
            return

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
            with self.device_lock:
                if self.device is not None:
                    send_layout_report(self.device, layout_index)
        except OSError as error:
            logging.error("Failed to send layout report: %s", error)
            self.close_device()
            return

        layer_name = "en" if layout_index == 0 else "ru"
        logging.info("Sent layout sync: %s (index %d)", layer_name, layout_index)
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
        logging.info("Layer state file: %s", self.state_file)

        self.start_reader()

        poll_interval = self.poll_interval_ms / 1000.0
        reconnect_interval = self.reconnect_delay_ms / 1000.0
        next_reconnect_at = datetime.min

        while not self.stop_event.is_set():
            self.sync_current_layout()

            if self.device is None and datetime.now() >= next_reconnect_at:
                self.ensure_device()
                next_reconnect_at = datetime.now() + timedelta(seconds=reconnect_interval)

            until = NSDate.dateWithTimeIntervalSinceNow_(poll_interval)
            NSRunLoop.currentRunLoop().runMode_beforeDate_(NSDefaultRunLoopMode, until)

    def stop(self) -> None:
        self.stop_event.set()
        self.close_device()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-c",
        "--layout-config",
        type=Path,
        default=DEFAULT_LAYOUT_CONFIG,
        help="Path to layout_sync.json",
    )
    parser.add_argument(
        "--layers-config",
        type=Path,
        default=DEFAULT_LAYERS_CONFIG,
        help="Path to layers.json",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help="Path to layer state JSON file",
    )
    parser.add_argument(
        "--layout-only",
        action="store_true",
        help="Only sync macOS layout to keyboard",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Sync layout once and exit",
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

    layout_config: dict = {}
    if args.layout_config.exists():
        layout_config = load_json_config(args.layout_config)
    elif not args.layout_only:
        logging.warning("Layout config not found: %s", args.layout_config)

    layers_config: list[dict] = []
    if args.layers_config.exists():
        layers_config = load_json_config(args.layers_config)
    elif not args.layout_only:
        logging.warning("Layers config not found: %s", args.layers_config)

    daemon = ZmkHidDaemon(
        layout_config=layout_config,
        layers_config=layers_config,
        state_file=args.state_file,
        read_layers=not args.layout_only,
        sync_layout=bool(layout_config.get("layouts")),
    )

    if args.once:
        daemon.run_once()
        daemon.stop()
        return 0

    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        logging.info("Stopped")
    finally:
        daemon.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
