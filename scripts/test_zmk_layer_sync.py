#!/usr/bin/env python3
"""Autotests for layer-sync daemon (Mac↔keyboard, no macime)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

ABC = "com.apple.keylayout.ABC"
RUSSIAN = "com.apple.keylayout.Russian"


class TestLayoutSyncHelpers(unittest.TestCase):
    def test_layout_index_for_source(self):
        from zmk_hid_daemon import layout_index_for_source

        layouts = [ABC, RUSSIAN]
        self.assertEqual(layout_index_for_source(ABC, layouts), 0)
        self.assertEqual(layout_index_for_source(RUSSIAN, layouts), 1)
        self.assertIsNone(layout_index_for_source("com.apple.keylayout.French", layouts))

    def test_write_layer_state(self):
        from zmk_hid_daemon import write_layer_state

        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            layers = [
                {"index": 0, "id": "en", "label": "EN"},
                {"index": 1, "id": "ru", "label": "RU"},
            ]
            write_layer_state(state_file, 1, layers, "velvet_v3_ui_ruen")
            state = json.loads(state_file.read_text())
            self.assertEqual(state["layer"], 1)
            self.assertEqual(state["id"], "ru")
            self.assertEqual(state["keyboard"], "velvet_v3_ui_ruen")


class TestZmkHidDaemon(unittest.TestCase):
    def _make_daemon(self, tmp_path: Path):
        from zmk_hid_daemon import ZmkHidDaemon

        layout_config = {
            "layouts": [ABC, RUSSIAN],
            "pause_sync_when_frontmost": ["Windows App"],
        }
        keyboards_config = {"default": "velvet_v3_ui_ruen", "keyboards": {}}
        return ZmkHidDaemon(
            layout_config=layout_config,
            keyboards_config=keyboards_config,
            scripts_dir=SCRIPTS_DIR,
            state_file=tmp_path / "state.json",
            read_layers=False,
            sync_layout=True,
        )

    def test_layer_report_updates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            daemon = self._make_daemon(Path(tmp))
            daemon.layers_config = [
                {"index": 0, "id": "en", "label": "EN"},
                {"index": 2, "id": "sym", "label": "SYM"},
            ]
            with patch("zmk_hid_daemon.trigger_sketchybar_update"):
                daemon._handle_report(bytes([0xAD, 2]))
            self.assertEqual(daemon.last_layer_index, 2)
            state = json.loads((Path(tmp) / "state.json").read_text())
            self.assertEqual(state["layer"], 2)

    def test_sync_sends_layout_to_keyboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            daemon = self._make_daemon(Path(tmp))
            mock_device = MagicMock()
            daemon.device = mock_device

            with patch("zmk_hid_daemon.current_input_source_id", return_value=RUSSIAN):
                with patch.object(daemon, "ensure_device", return_value=True):
                    daemon.sync_current_layout()

            self.assertEqual(daemon.last_sent_index, 1)
            mock_device.write.assert_called_once()
            report = mock_device.write.call_args[0][0]
            self.assertEqual(report[1], 0xAC)
            self.assertEqual(report[2], 1)

    def test_sync_skips_duplicate_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            daemon = self._make_daemon(Path(tmp))
            daemon.last_sent_index = 0
            mock_device = MagicMock()
            daemon.device = mock_device

            with patch("zmk_hid_daemon.current_input_source_id", return_value=ABC):
                with patch.object(daemon, "ensure_device", return_value=True):
                    daemon.sync_current_layout()

            mock_device.write.assert_not_called()

    def test_sync_pauses_for_frontmost_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            daemon = self._make_daemon(Path(tmp))
            mock_device = MagicMock()
            daemon.device = mock_device

            with patch("zmk_hid_daemon.current_input_source_id", return_value=RUSSIAN):
                with patch("zmk_hid_daemon.frontmost_app_name", return_value="Windows App"):
                    daemon.sync_current_layout()

            mock_device.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
