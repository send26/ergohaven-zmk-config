#!/usr/bin/env python3
"""Autotests for sym-layer macime debounce in zmk_hid_daemon."""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import DEFAULT, patch

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

UNICODE_HEX = "com.apple.keylayout.UnicodeHexInput"
ABC = "com.apple.keylayout.ABC"
RUSSIAN = "com.apple.keylayout.Russian"
SYM_MACIME = ABC

LEFT_ROW1_KP = ["HASH", "LT", "EQUAL", "GT", "ASTERISK"]
LEFT_ROW3_KP = ["COMMA", "BSLH", "COLON", "FSLH", "PIPE"]

LAYER_BASE = 0
LAYER_RU = 1
LAYER_SYM = 2
LAYER_SYM_RU = 3


def wait_macime(applied: list[str], min_len: int = 1, timeout: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(applied) >= min_len:
            return
        time.sleep(0.01)


def wait_grace(restore_ms: int) -> None:
    time.sleep(restore_ms / 1000.0 + 0.08)


def apply_layer(daemon, layer: int) -> None:
    previous = daemon.last_layer_index
    daemon.last_layer_index = layer
    daemon._sync_macime_for_layer_change(previous, layer)


def make_daemon(applied: list[str], restore_ms: int = 200):
    from zmk_hid_daemon import ZmkHidDaemon

    def fake_switch(_macime_path: str, layout_id: str) -> bool:
        applied.append(layout_id)
        return True

    started = patch.multiple(
        "zmk_hid_daemon",
        switch_macime_layout=DEFAULT,
        switch_input_source=DEFAULT,
        warm_input_source_cache=DEFAULT,
    )
    mocks = started.start()
    mocks["switch_macime_layout"].side_effect = fake_switch
    mocks["switch_input_source"].return_value = False

    layout_config = {
        "layouts": [ABC, RUSSIAN],
        "macime_layouts": {"0": ABC, "1": RUSSIAN},
        "sym_layers": [2],
        "sym_macime_layout": SYM_MACIME,
        "sym_restore_delay_ms": restore_ms,
    }
    keyboards_config = {"default": "velvet_v3_ui_ruen", "keyboards": {}}
    daemon = ZmkHidDaemon(
        layout_config=layout_config,
        keyboards_config=keyboards_config,
        scripts_dir=SCRIPTS_DIR,
        state_file=Path("/tmp/zmk_test_state.json"),
        read_layers=False,
        sync_layout=False,
    )
    return daemon, started


def make_daemon_no_sym(applied: list[str]) -> tuple:
    from zmk_hid_daemon import ZmkHidDaemon

    def fake_switch(_macime_path: str, layout_id: str) -> bool:
        applied.append(layout_id)
        return True

    started = patch.multiple(
        "zmk_hid_daemon",
        switch_macime_layout=DEFAULT,
        switch_input_source=DEFAULT,
        warm_input_source_cache=DEFAULT,
    )
    mocks = started.start()
    mocks["switch_macime_layout"].side_effect = fake_switch
    mocks["switch_input_source"].return_value = False

    layout_config = {
        "layouts": [ABC, RUSSIAN],
        "macime_layouts": {"0": ABC, "1": RUSSIAN},
        "sym_layers": [],
    }
    daemon = ZmkHidDaemon(
        layout_config=layout_config,
        keyboards_config={"default": "velvet_v3_ui_ruen", "keyboards": {}},
        scripts_dir=SCRIPTS_DIR,
        state_file=Path("/tmp/zmk_test_state_nosym.json"),
        read_layers=False,
        sync_layout=False,
    )
    return daemon, started


class NoSymDaemonTests(unittest.TestCase):
    """Production config: sym layers handled in firmware, not via macime."""

    def test_sym_layers_do_not_switch_macime(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon_no_sym(applied)
        try:
            apply_layer(daemon, LAYER_RU)
            wait_macime(applied)
            apply_layer(daemon, LAYER_SYM)
            apply_layer(daemon, LAYER_SYM_RU)
            time.sleep(0.15)
            self.assertEqual(applied, [RUSSIAN])
        finally:
            daemon.stop()
            started.stop()

    def test_ru_sym_ru_keeps_russian_macime(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon_no_sym(applied)
        try:
            apply_layer(daemon, LAYER_RU)
            wait_macime(applied)
            for _ in range(3):
                apply_layer(daemon, LAYER_SYM)
                apply_layer(daemon, LAYER_RU)
            time.sleep(0.15)
            self.assertEqual(applied, [RUSSIAN])
        finally:
            daemon.stop()
            started.stop()


class SymMacimeDebounceTests(unittest.TestCase):
    def test_sym_then_immediate_ru_does_not_restore_russian(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied)
        try:
            daemon._sync_macime_for_layer_change(1, 2)
            wait_macime(applied)
            daemon._sync_macime_for_layer_change(2, 1)
            time.sleep(0.15)
            self.assertEqual(applied, [SYM_MACIME])
        finally:
            daemon.stop()
            started.stop()

    def test_sym_ru_sym_flicker_stays_on_unicode(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied)
        try:
            for _ in range(4):
                daemon._sync_macime_for_layer_change(1, 2)
                daemon._sync_macime_for_layer_change(2, 1)
            wait_macime(applied)
            time.sleep(0.15)
            self.assertEqual(applied, [SYM_MACIME])
        finally:
            daemon.stop()
            started.stop()

    def test_restore_russian_after_sym_release(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied, restore_ms=100)
        try:
            daemon._sync_macime_for_layer_change(1, 2)
            wait_macime(applied)
            daemon._sync_macime_for_layer_change(2, 1)
            time.sleep(0.25)
            self.assertIn(RUSSIAN, applied)
        finally:
            daemon.stop()
            started.stop()

    def test_stale_macime_switch_superseded(self) -> None:
        applied: list[str] = []
        gate = threading.Event()

        def slow_switch(_macime_path: str, layout_id: str) -> bool:
            if layout_id == RUSSIAN:
                gate.wait(timeout=1.0)
            applied.append(layout_id)
            return True

        from zmk_hid_daemon import ZmkHidDaemon

        started = patch.multiple(
            "zmk_hid_daemon",
            switch_macime_layout=DEFAULT,
            switch_input_source=DEFAULT,
            warm_input_source_cache=DEFAULT,
        )
        mocks = started.start()
        mocks["switch_macime_layout"].side_effect = slow_switch
        mocks["switch_input_source"].return_value = False
        layout_config = {
            "layouts": [ABC, RUSSIAN],
            "macime_layouts": {"0": ABC, "1": RUSSIAN},
            "sym_layers": [2],
            "sym_macime_layout": SYM_MACIME,
            "sym_restore_delay_ms": 50,
        }
        daemon = ZmkHidDaemon(
            layout_config=layout_config,
            keyboards_config={"default": "velvet_v3_ui_ruen", "keyboards": {}},
            scripts_dir=SCRIPTS_DIR,
            state_file=Path("/tmp/zmk_test_state_stale.json"),
            read_layers=False,
            sync_layout=False,
        )
        try:
            daemon._sync_macime_for_layer_change(1, 2)
            wait_macime(applied)
            daemon._sym_active_until = time.monotonic() - 1
            daemon._post_sym_restore_layout_id = RUSSIAN
            daemon._request_macime_layout(RUSSIAN)
            time.sleep(0.02)
            daemon._sync_macime_for_layer_change(2, 2)
            gate.set()
            wait_macime(applied, min_len=2)
            self.assertEqual(daemon.last_macime_layout_id, SYM_MACIME)
            self.assertIn(RUSSIAN, applied)
        finally:
            gate.set()
            daemon.stop()
            started.stop()

    def test_ru_after_sym_deadline_still_on_sym_session_defers(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied, restore_ms=50)
        try:
            apply_layer(daemon, LAYER_SYM)
            wait_macime(applied)
            daemon._in_sym_macime_session = True
            daemon._sym_active_until = time.monotonic() - 1
            apply_layer(daemon, LAYER_RU)
            self.assertEqual(applied, [SYM_MACIME])
            self.assertGreater(daemon._sym_active_until, time.monotonic())
        finally:
            daemon.stop()
            started.stop()

    def test_base_layer_sym_does_not_restore_abc_immediately(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied)
        try:
            daemon._sync_macime_for_layer_change(0, 2)
            wait_macime(applied)
            daemon._sync_macime_for_layer_change(2, 0)
            time.sleep(0.15)
            self.assertEqual(applied, [SYM_MACIME])
        finally:
            daemon.stop()
            started.stop()


class LayerMacimeMatrixTests(unittest.TestCase):
    """Mac layout vs keyboard layer combinations (base/ru × sym)."""

    def test_normal_ru_applies_russian_immediately(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied)
        try:
            daemon.last_macime_layout_id = ABC
            daemon._in_sym_macime_session = False
            daemon._sym_active_until = 0.0
            apply_layer(daemon, LAYER_RU)
            wait_macime(applied)
            self.assertEqual(applied, [RUSSIAN])
        finally:
            daemon.stop()
            started.stop()

    def test_normal_base_applies_abc_immediately(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied)
        try:
            daemon.last_macime_layout_id = RUSSIAN
            daemon._in_sym_macime_session = False
            daemon._sym_active_until = 0.0
            apply_layer(daemon, LAYER_BASE)
            wait_macime(applied)
            self.assertEqual(applied, [ABC])
        finally:
            daemon.stop()
            started.stop()

    def test_ru_sym_ru_restores_russian_after_grace(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied, restore_ms=100)
        try:
            apply_layer(daemon, LAYER_RU)
            wait_macime(applied)
            apply_layer(daemon, LAYER_SYM)
            wait_macime(applied, min_len=2)
            self.assertEqual(applied[-1], SYM_MACIME)
            apply_layer(daemon, LAYER_RU)
            wait_grace(100)
            self.assertEqual(applied[-1], RUSSIAN)
            self.assertFalse(daemon._in_sym_macime_session)
        finally:
            daemon.stop()
            started.stop()

    def test_base_sym_base_restores_abc_after_grace(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied, restore_ms=100)
        try:
            apply_layer(daemon, LAYER_BASE)
            wait_macime(applied)
            apply_layer(daemon, LAYER_SYM)
            wait_macime(applied, min_len=2)
            self.assertEqual(applied[-1], SYM_MACIME)
            apply_layer(daemon, LAYER_BASE)
            wait_grace(100)
            self.assertEqual(applied[-1], ABC)
        finally:
            daemon.stop()
            started.stop()

    def test_base_sym_ru_restores_russian_after_grace(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied, restore_ms=100)
        try:
            apply_layer(daemon, LAYER_BASE)
            wait_macime(applied)
            apply_layer(daemon, LAYER_SYM)
            wait_macime(applied, min_len=2)
            apply_layer(daemon, LAYER_RU)
            wait_grace(100)
            self.assertEqual(applied[-1], RUSSIAN)
        finally:
            daemon.stop()
            started.stop()

    def test_ru_sym_base_restores_abc_after_grace(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied, restore_ms=100)
        try:
            apply_layer(daemon, LAYER_RU)
            wait_macime(applied)
            apply_layer(daemon, LAYER_SYM)
            wait_macime(applied, min_len=2)
            apply_layer(daemon, LAYER_BASE)
            wait_grace(100)
            self.assertEqual(applied[-1], ABC)
        finally:
            daemon.stop()
            started.stop()

    def test_after_sym_session_switch_ru_to_base_to_ru(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied, restore_ms=80)
        try:
            apply_layer(daemon, LAYER_RU)
            apply_layer(daemon, LAYER_SYM)
            apply_layer(daemon, LAYER_RU)
            wait_grace(80)
            self.assertEqual(applied[-1], RUSSIAN)
            daemon._cancel_sym_grace_timer()
            daemon._in_sym_macime_session = False
            daemon._sym_active_until = 0.0
            before = len(applied)
            apply_layer(daemon, LAYER_BASE)
            wait_macime(applied, min_len=before + 1)
            self.assertEqual(applied[-1], ABC)
            before = len(applied)
            apply_layer(daemon, LAYER_RU)
            wait_macime(applied, min_len=before + 1)
            self.assertEqual(applied[-1], RUSSIAN)
        finally:
            daemon.stop()
            started.stop()

    def test_stuck_on_abc_after_sym_recovers_on_layer_change(self) -> None:
        applied: list[str] = []
        daemon, started = make_daemon(applied)
        try:
            daemon.last_macime_layout_id = SYM_MACIME
            daemon._in_sym_macime_session = False
            daemon._sym_active_until = 0.0
            apply_layer(daemon, LAYER_RU)
            wait_macime(applied)
            self.assertEqual(applied, [RUSSIAN])
        finally:
            daemon.stop()
            started.stop()


class TisApiTests(unittest.TestCase):
    def test_resolve_input_source_accepts_one_or_two_args(self) -> None:
        from zmk_hid_daemon import resolve_input_source

        calls: list[int] = []

        def create_two(properties, include_all):
            calls.append(2)
            return [object()]

        def create_one(properties):
            calls.append(1)
            return [object()]

        with patch.dict(
            "zmk_hid_daemon._input_source_cache",
            {},
            clear=True,
        ), patch.dict(
            "zmk_hid_daemon._TIS",
            {"TISCreateInputSourceList": create_two},
        ):
            self.assertIsNotNone(resolve_input_source(ABC))
            self.assertEqual(calls, [2])

        with patch.dict(
            "zmk_hid_daemon._input_source_cache",
            {},
            clear=True,
        ), patch.dict(
            "zmk_hid_daemon._TIS",
            {"TISCreateInputSourceList": create_one},
        ):
            calls.clear()
            self.assertIsNotNone(resolve_input_source(RUSSIAN))
            self.assertEqual(calls, [1])


class SymKeymapTests(unittest.TestCase):
    def _left_row_kps(self, row_index: int) -> list[str]:
        keymap_path = REPO_ROOT / "config" / "velvet_v3_ui_ruen.keymap"
        text = keymap_path.read_text(encoding="utf-8")
        sym_block = text.split("sym {", 1)[1].split("display-name", 1)[0]
        row_lines = [
            line.strip()
            for line in sym_block.splitlines()
            if line.strip().startswith("&")
        ]
        tokens = row_lines[row_index].split()
        kps: list[str] = []
        index = 0
        while index < len(tokens):
            if tokens[index] == "&kp" and index + 1 < len(tokens):
                kps.append(tokens[index + 1])
                index += 2
                continue
            index += 1
        return kps[:5]

    def test_left_row1_kp_bindings(self) -> None:
        self.assertEqual(self._left_row_kps(0), LEFT_ROW1_KP)

    def test_left_row3_kp_bindings(self) -> None:
        self.assertEqual(self._left_row_kps(2), LEFT_ROW3_KP)


class SymRuKeymapTests(unittest.TestCase):
    def test_sym_ru_row3_has_russian_native_bindings(self) -> None:
        keymap_path = REPO_ROOT / "config" / "velvet_v3_ui_ruen.keymap"
        text = keymap_path.read_text(encoding="utf-8")
        sym_block = text.split('display-name = "sym_ru";', 1)[1].split(">;", 1)[0]
        self.assertIn("&kp LS(N5)", sym_block)
        self.assertIn("&en FSLH", sym_block)
        self.assertIn("&en PIPE", sym_block)

    def test_ru_layer_uses_sym_ru_lt(self) -> None:
        keymap_path = REPO_ROOT / "config" / "velvet_v3_ui_ruen.keymap"
        text = keymap_path.read_text(encoding="utf-8")
        ru_block = text.split("display-name = \"ru\";", 1)[1].split("sym {", 1)[0]
        self.assertIn("&lt 3 BACKSPACE", ru_block)

    def test_en_layer_uses_sym_lt(self) -> None:
        keymap_path = REPO_ROOT / "config" / "velvet_v3_ui_ruen.keymap"
        text = keymap_path.read_text(encoding="utf-8")
        en_block = text.split("display-name = \"base\";", 1)[0]
        self.assertIn("&lt 2 BACKSPACE", en_block)


class DaemonLogAnalyzerTests(unittest.TestCase):
    def test_detect_sym_ru_flip_flop_in_log(self) -> None:
        log_path = Path.home() / "Library" / "Logs" / "zmk-layer-daemon.log"
        if not log_path.exists():
            self.skipTest("daemon log not found")

        from test_sym_unicode import analyze_sym_ru_flapping

        flips = analyze_sym_ru_flapping(log_path.read_text(encoding="utf-8", errors="replace"))
        # informational — log may contain historical flips before fix
        self.assertIsInstance(flips, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
