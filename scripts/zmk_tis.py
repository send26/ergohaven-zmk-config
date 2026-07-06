"""macOS Text Input Source helpers (TIS API + macime fallback)."""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import subprocess
import time
from pathlib import Path

import objc
from Foundation import NSBundle, NSDictionary

DEFAULT_MACIME_PATH = "/usr/local/bin/macime"

_input_source_cache: dict[str, object] = {}


def _load_tis_api_ctypes() -> dict:
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

    carbon.TISCreateInputSourceList.restype = ctypes.c_void_p
    carbon.TISCreateInputSourceList.argtypes = [ctypes.c_void_p, ctypes.c_bool]

    carbon.TISSelectInputSource.restype = ctypes.c_uint32
    carbon.TISSelectInputSource.argtypes = [ctypes.c_void_p]

    input_source_id_key = ctypes.c_void_p.in_dll(carbon, "kTISPropertyInputSourceID")

    def copy_current_keyboard_input_source():
        return objcify(carbon.TISCopyCurrentKeyboardInputSource())

    def create_input_source_list(properties, include_all: bool):
        return objcify(
            carbon.TISCreateInputSourceList(properties.__c_void_p__(), include_all)
        )

    def select_input_source_ref(source) -> int:
        return int(carbon.TISSelectInputSource(source.__c_void_p__()))

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
        "TISCreateInputSourceList": create_input_source_list,
        "TISSelectInputSource": select_input_source_ref,
        "TISGetInputSourceProperty": get_input_source_property,
        "kTISPropertyInputSourceID": input_source_id_key,
    }


def _load_tis_api() -> dict:
    try:
        from HIToolbox import (
            TISCopyCurrentKeyboardInputSource,
            TISCreateInputSourceList,
            TISGetInputSourceProperty,
            TISSelectInputSource,
            kTISPropertyInputSourceID,
        )

        return {
            "TISCopyCurrentKeyboardInputSource": TISCopyCurrentKeyboardInputSource,
            "TISCreateInputSourceList": TISCreateInputSourceList,
            "TISSelectInputSource": TISSelectInputSource,
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
                    ("TISCreateInputSourceList", b"@B"),
                    ("TISSelectInputSource", b"i@"),
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


def resolve_input_source(layout_id: str) -> object | None:
    if layout_id in _input_source_cache:
        return _input_source_cache[layout_id]

    create_list = _TIS.get("TISCreateInputSourceList")
    if create_list is None:
        return None

    properties = NSDictionary.dictionaryWithDictionary_(
        {"TISPropertyInputSourceID": layout_id}
    )
    try:
        source_list = create_list(properties, False)
    except TypeError:
        source_list = create_list(properties)
    if source_list is None or len(source_list) == 0:
        return None

    source = source_list[0]
    _input_source_cache[layout_id] = source
    return source


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


def switch_input_source(layout_id: str, wait_ms: int = 80) -> bool:
    source = resolve_input_source(layout_id)
    select = _TIS.get("TISSelectInputSource")
    if source is None or select is None:
        return False

    started = time.monotonic()
    status = select(source)
    if status != 0:
        return False

    deadline = started + wait_ms / 1000.0
    while time.monotonic() < deadline:
        if current_input_source_id() == layout_id:
            break
        time.sleep(0.005)

    elapsed_ms = (time.monotonic() - started) * 1000
    logging.info("TIS → %s (%.0fms)", layout_id, elapsed_ms)
    return True


def warm_input_source_cache(layout_ids: set[str]) -> None:
    for layout_id in layout_ids:
        try:
            resolve_input_source(layout_id)
        except Exception as error:
            logging.debug("Input source cache warmup skipped for %s: %s", layout_id, error)


def switch_macime_layout(macime_path: str, layout_id: str) -> bool:
    try:
        if switch_input_source(layout_id):
            return True
    except Exception as error:
        logging.debug("TIS switch failed for %s: %s", layout_id, error)

    if not Path(macime_path).exists():
        logging.warning("macime not found: %s", macime_path)
        return False
    try:
        result = subprocess.run(
            [macime_path, "set", layout_id],
            check=False,
            capture_output=True,
            text=True,
        )
        combined = f"{result.stdout}\n{result.stderr}".strip()
        failure_markers = ("Invalid sub command", "IME not found", "Error:")
        if any(marker in combined for marker in failure_markers):
            logging.warning(
                "macime set %s failed (exit %s): %s",
                layout_id,
                result.returncode,
                combined,
            )
            return False
        logging.info("macime → %s", layout_id)
        return True
    except OSError as error:
        logging.warning("macime failed: %s", error)
        return False
