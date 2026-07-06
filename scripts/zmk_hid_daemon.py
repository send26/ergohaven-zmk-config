#!/usr/bin/env python3
"""ZMK Raw HID daemon: keyboard layer reporting + Mac↔keyboard layout sync."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import hid
import objc
from AppKit import NSDate, NSDefaultRunLoopMode, NSRunLoop, NSWorkspace
from Foundation import NSDistributedNotificationCenter, NSObject

from zmk_tis import current_input_source_id, switch_macime_layout

RAW_HID_USAGE_PAGE = 0xFF60
RAW_HID_USAGE = 0x61
HID_CMD_LAYOUT = 0xAC
HID_CMD_LAYER = 0xAD
REPORT_SIZE = 32

DEFAULT_LAYOUT_CONFIG = Path(__file__).with_name("layout_sync.json")
DEFAULT_KEYBOARDS_CONFIG = Path(__file__).with_name("keyboards.json")
DEFAULT_LAYERS_CONFIG = Path(__file__).with_name("layers.json")
DEFAULT_STATE_DIR = Path.home() / ".cache" / "zmk_layer"
DEFAULT_STATE_FILE = DEFAULT_STATE_DIR / "state.json"
DEFAULT_MACIME_PATH = "/usr/local/bin/macime"
DEFAULT_MACIME_LAYOUTS = {
    0: "com.apple.keylayout.ABC",
    1: "com.apple.keylayout.Russian",
}

INPUT_SOURCE_NOTIFICATIONS = (
    "com.apple.inputmethodKit.IMKClient.currentInputSourceDidChange",
    "com.apple.system.config.keyboard.layoutchanged",
)


def load_json_config(path: Path) -> dict | list:
    with path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


def frontmost_app_name() -> str | None:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    return str(app.localizedName())


def should_pause_host_layout_sync(pause_apps: list[str]) -> bool:
    if not pause_apps:
        return False
    frontmost = frontmost_app_name()
    if frontmost is None:
        return False
    return frontmost in pause_apps


def layout_index_for_source(source_id: str, layouts: list[str]) -> int | None:
    try:
        return layouts.index(source_id)
    except ValueError:
        return None


def find_raw_hid_device() -> tuple[hid.Device, dict] | None:
    for device_info in hid.enumerate():
        if (
            device_info.get("usage_page") == RAW_HID_USAGE_PAGE
            and device_info.get("usage") == RAW_HID_USAGE
        ):
            return hid.Device(path=device_info["path"]), device_info
    return None


def detect_keyboard(
    device_info: dict,
    keyboards_config: dict,
    override: str | None = None,
) -> str:
    if override:
        return override

    keyboards = keyboards_config.get("keyboards", {})
    haystack = " ".join(
        str(device_info.get(key, "") or "")
        for key in ("manufacturer_string", "product_string", "product", "manufacturer", "serial_number")
    ).lower()

    for keyboard_id, keyboard in keyboards.items():
        for needle in keyboard.get("match", []):
            if needle.lower() in haystack:
                return keyboard_id

    return keyboards_config.get("default", next(iter(keyboards), ""))


def layers_file_for_keyboard(keyboards_config: dict, keyboard_id: str, scripts_dir: Path) -> Path:
    keyboard = keyboards_config.get("keyboards", {}).get(keyboard_id, {})
    layers_file = keyboard.get("layers_file", "layers.json")
    return scripts_dir / layers_file


def load_layers_for_keyboard(keyboards_config: dict, keyboard_id: str, scripts_dir: Path) -> list[dict]:
    layers_path = layers_file_for_keyboard(keyboards_config, keyboard_id, scripts_dir)
    if not layers_path.exists():
        logging.warning("Layers file not found for %s: %s", keyboard_id, layers_path)
        return []
    return load_json_config(layers_path)


def write_layer_state(
    state_file: Path,
    layer_index: int,
    layers_config: list[dict],
    keyboard_id: str,
) -> None:
    layer_meta = next((layer for layer in layers_config if layer["index"] == layer_index), None)
    state = {
        "keyboard": keyboard_id,
        "layer": layer_index,
        "id": layer_meta["id"] if layer_meta else f"layer_{layer_index}",
        "label": layer_meta["label"] if layer_meta else f"L{layer_index}",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state) + "\n", encoding="utf-8")


def send_layout_report(device: hid.Device, layout_index: int) -> None:
    payload = [HID_CMD_LAYOUT, layout_index] + [0x00] * (REPORT_SIZE - 2)
    report = bytes([0x00] + payload)
    device.write(report)


def find_sketchybar() -> str | None:
    for candidate in (
        "/opt/homebrew/bin/sketchybar",
        "/usr/local/bin/sketchybar",
        shutil.which("sketchybar"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def trigger_sketchybar_update() -> None:
    sketchybar = find_sketchybar()
    if sketchybar is None:
        logging.warning("SketchyBar binary not found, skipping trigger")
        return

    try:
        result = subprocess.run(
            [sketchybar, "--trigger", "zmk_layer_update"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logging.warning(
                "SketchyBar trigger failed (%s): %s",
                result.returncode,
                result.stderr.strip(),
            )
    except OSError as error:
        logging.warning("SketchyBar trigger failed: %s", error)


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
        keyboards_config: dict,
        scripts_dir: Path,
        state_file: Path,
        keyboard_override: str | None = None,
        read_layers: bool = True,
        sync_layout: bool = True,
    ) -> None:
        self.layouts: list[str] = layout_config.get("layouts", [])
        self.poll_interval_ms: int = layout_config.get("poll_interval_ms", 500)
        self.reconnect_delay_ms: int = layout_config.get("reconnect_delay_ms", 3000)
        self.keyboards_config = keyboards_config
        self.scripts_dir = scripts_dir
        self.keyboard_override = keyboard_override
        self.state_file = state_file
        self.read_layers = read_layers
        self.sync_layout = sync_layout
        self.pause_sync_when_frontmost: list[str] = layout_config.get(
            "pause_sync_when_frontmost", []
        )
        self.macime_path: str = layout_config.get("macime_path", DEFAULT_MACIME_PATH)
        raw_macime_layouts = layout_config.get("macime_layouts", DEFAULT_MACIME_LAYOUTS)
        self.macime_layouts: dict[int | str, str] = {
            int(key) if str(key).isdigit() else key: value
            for key, value in raw_macime_layouts.items()
        }
        self.sym_layers: set[int] = set(layout_config.get("sym_layers", [2, 3]))

        self.active_keyboard = keyboard_override or keyboards_config.get("default", "")
        self.layers_config = load_layers_for_keyboard(
            keyboards_config,
            self.active_keyboard,
            scripts_dir,
        )

        self.device: hid.Device | None = None
        self.device_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.read_thread: threading.Thread | None = None

        self.last_source_id: str | None = None
        self.last_sent_index: int | None = None
        self.last_layer_index: int | None = None
        self._suppress_mac_to_keyboard_until: float = 0.0

    def _layout_id_for_layer(self, layer_index: int) -> str | None:
        return self.macime_layouts.get(layer_index) or self.macime_layouts.get(
            str(layer_index)
        )

    def _sync_mac_layout_for_layer(self, layer_index: int) -> None:
        if layer_index in self.sym_layers:
            return
        layout_id = self._layout_id_for_layer(layer_index)
        if layout_id is None:
            return
        if current_input_source_id() == layout_id:
            logging.debug("Mac layout already %s for layer %d", layout_id, layer_index)
            return
        if switch_macime_layout(self.macime_path, layout_id):
            self.last_source_id = layout_id
            self._suppress_mac_to_keyboard_until = time.monotonic() + 1.5
            logging.info("Keyboard layer %d → Mac %s", layer_index, layout_id)

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

            found = find_raw_hid_device()
            if found is None:
                return False

            self.device, device_info = found

            try:
                self.device.nonblocking = True
            except AttributeError:
                pass

            keyboard_id = detect_keyboard(
                device_info,
                self.keyboards_config,
                self.keyboard_override,
            )
            if keyboard_id != self.active_keyboard:
                self.active_keyboard = keyboard_id
                self.layers_config = load_layers_for_keyboard(
                    self.keyboards_config,
                    keyboard_id,
                    self.scripts_dir,
                )
                self.last_layer_index = None
                logging.info("Active keyboard profile: %s", keyboard_id)

            manufacturer = self.device.manufacturer or device_info.get("manufacturer_string") or "unknown"
            product = self.device.product or device_info.get("product_string") or "unknown"
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
                data = device.read(REPORT_SIZE, timeout=500)
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
        write_layer_state(
            self.state_file,
            layer_index,
            self.layers_config,
            self.active_keyboard,
        )
        logging.info(
            "Layer update [%s]: %s (index %d)",
            self.active_keyboard,
            layer_label,
            layer_index,
        )
        if layer_index in (0, 1):
            self._sync_mac_layout_for_layer(layer_index)
        trigger_sketchybar_update()

    def sync_current_layout(self) -> None:
        if not self.sync_layout or not self.layouts:
            return

        if should_pause_host_layout_sync(self.pause_sync_when_frontmost):
            logging.debug(
                "Skipping Mac→keyboard sync while %s is frontmost",
                frontmost_app_name(),
            )
            return

        if (
            self.last_layer_index is not None
            and self.last_layer_index in self.sym_layers
        ):
            source_id = current_input_source_id()
            if source_id and source_id != self.last_source_id:
                logging.debug(
                    "Skipping Mac→keyboard sync while on sym layer %d",
                    self.last_layer_index,
                )
                self.last_source_id = source_id
            return

        if time.monotonic() < self._suppress_mac_to_keyboard_until:
            source_id = current_input_source_id()
            if source_id and source_id != self.last_source_id:
                logging.debug("Skipping Mac→keyboard echo after keyboard layer switch")
                self.last_source_id = source_id
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
        logging.info("Active keyboard profile: %s", self.active_keyboard)
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
        "--keyboards-config",
        type=Path,
        default=DEFAULT_KEYBOARDS_CONFIG,
        help="Path to keyboards.json",
    )
    parser.add_argument(
        "--keyboard",
        default=os.environ.get("ZMK_KEYBOARD"),
        help="Force keyboard profile (e.g. op36_ruen, velvet_v3_ui_ruen)",
    )
    parser.add_argument(
        "--layers-config",
        type=Path,
        default=DEFAULT_LAYERS_CONFIG,
        help="Deprecated fallback layers.json path",
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

    keyboards_config: dict = {"default": "velvet_v3_ui_ruen", "keyboards": {}}
    if args.keyboards_config.exists():
        keyboards_config = load_json_config(args.keyboards_config)
    elif not args.layout_only:
        logging.warning("Keyboards config not found: %s", args.keyboards_config)

    scripts_dir = args.keyboards_config.parent

    daemon = ZmkHidDaemon(
        layout_config=layout_config,
        keyboards_config=keyboards_config,
        scripts_dir=scripts_dir,
        state_file=args.state_file,
        keyboard_override=args.keyboard,
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
