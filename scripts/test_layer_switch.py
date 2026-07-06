#!/usr/bin/env python3
"""Keymap + daemon tests: layer switch must not emit Ctrl+Shift digit shortcuts."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
CONFIG_DIR = REPO_ROOT / "config"
sys.path.insert(0, str(SCRIPTS_DIR))

RUEN_KEYMAPS = [
    CONFIG_DIR / "velvet_v3_ui_ruen.keymap",
    CONFIG_DIR / "velvet_v3_ruen.keymap",
    CONFIG_DIR / "k03_ruen.keymap",
    CONFIG_DIR / "imperial44_ruen.keymap",
    CONFIG_DIR / "op36_ruen.keymap",
    CONFIG_DIR / "ruen.dtsi",
]

LAYER_MACRO_RE = re.compile(
    r"(layer_(?:en|ru)):\s*\1\s*\{.*?bindings\s*=\s*<([^>]+)>",
    re.DOTALL,
)
FORBIDDEN_BINDING_MARKERS = (
    "&to_en",
    "&to_ru",
    "LS(LC(N1))",
    "LS(LC(N2))",
    "LC(N1)",
    "LC(N2)",
)

# On Russian macOS layout Shift+2 types QUOTEDBL — root cause of garbage on layer_ru+to_ru.
RUSSIAN_SHIFT_DIGIT_CHARS = {
    "1": "!",
    "2": '"',
    "3": "№",
    "4": "%",
    "5": ":",
    "6": ",",
    "7": ".",
    "8": ";",
    "9": "(",
    "0": ")",
}


def parse_layer_macro_bindings(keymap_text: str) -> dict[str, str]:
    macros_match = re.search(r"macros\s*\{", keymap_text)
    if macros_match is None:
        return {}
    start = macros_match.end()
    depth = 1
    index = start
    while index < len(keymap_text) and depth:
        char = keymap_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    macros_block = keymap_text[start : index - 1]
    return {
        match.group(1): match.group(2).replace("\n", " ").strip()
        for match in LAYER_MACRO_RE.finditer(macros_block)
    }


class TestKeymapLayerSwitch(unittest.TestCase):
    def test_layer_macros_have_no_layout_shortcuts(self) -> None:
        for keymap_path in RUEN_KEYMAPS:
            if not keymap_path.exists():
                continue
            bindings_by_macro = parse_layer_macro_bindings(keymap_path.read_text(encoding="utf-8"))
            for macro_name in ("layer_en", "layer_ru"):
                if macro_name not in bindings_by_macro:
                    continue
                bindings = bindings_by_macro[macro_name]
                with self.subTest(keymap=keymap_path.name, macro=macro_name, bindings=bindings):
                    for marker in FORBIDDEN_BINDING_MARKERS:
                        self.assertNotIn(
                            marker,
                            bindings,
                            f"{keymap_path.name} {macro_name} must not send layout shortcut ({marker})",
                        )

    def test_layer_en_only_switches_to_0(self) -> None:
        velvet = CONFIG_DIR / "velvet_v3_ui_ruen.keymap"
        bindings = parse_layer_macro_bindings(velvet.read_text(encoding="utf-8"))
        self.assertIn("&to 0", bindings["layer_en"])
        self.assertNotIn("&to 1", bindings["layer_en"])

    def test_layer_ru_only_switches_to_1(self) -> None:
        velvet = CONFIG_DIR / "velvet_v3_ui_ruen.keymap"
        bindings = parse_layer_macro_bindings(velvet.read_text(encoding="utf-8"))
        self.assertIn("&to 1", bindings["layer_ru"])
        self.assertNotIn("&to 0", bindings["layer_ru"])

    def test_russian_shift2_produces_quotedbl(self) -> None:
        """Documents why Ctrl+Shift+2 from firmware leaks garbage on Russian Mac layout."""
        self.assertEqual(RUSSIAN_SHIFT_DIGIT_CHARS["2"], '"')


class TestLayerSwitchDaemon(unittest.TestCase):
    def test_layer_ru_report_switches_mac_without_shortcut(self) -> None:
        from unittest.mock import patch

        from zmk_hid_daemon import ZmkHidDaemon

        applied: list[str] = []

        def fake_switch(_path: str, layout_id: str) -> bool:
            applied.append(layout_id)
            return True

        layout_config = {
            "layouts": [
                "com.apple.keylayout.ABC",
                "com.apple.keylayout.Russian",
            ],
            "macime_layouts": {"0": "com.apple.keylayout.ABC", "1": "com.apple.keylayout.Russian"},
            "sym_layers": [2, 3],
        }
        daemon = ZmkHidDaemon(
            layout_config=layout_config,
            keyboards_config={"default": "velvet_v3_ui_ruen", "keyboards": {}},
            scripts_dir=SCRIPTS_DIR,
            state_file=Path("/tmp/zmk_layer_switch_test.json"),
            read_layers=False,
            sync_layout=True,
        )
        with patch("zmk_hid_daemon.current_input_source_id", return_value="com.apple.keylayout.ABC"):
            with patch("zmk_hid_daemon.switch_macime_layout", side_effect=fake_switch):
                with patch("zmk_hid_daemon.trigger_sketchybar_update"):
                    daemon._handle_report(bytes([0xAD, 1]))
        self.assertEqual(applied, ["com.apple.keylayout.Russian"])

    def test_sym_layer_does_not_switch_mac(self) -> None:
        from unittest.mock import patch

        from zmk_hid_daemon import ZmkHidDaemon

        layout_config = {
            "layouts": ["com.apple.keylayout.ABC", "com.apple.keylayout.Russian"],
            "macime_layouts": {"0": "com.apple.keylayout.ABC", "1": "com.apple.keylayout.Russian"},
            "sym_layers": [2, 3],
        }
        daemon = ZmkHidDaemon(
            layout_config=layout_config,
            keyboards_config={"default": "velvet_v3_ui_ruen", "keyboards": {}},
            scripts_dir=SCRIPTS_DIR,
            state_file=Path("/tmp/zmk_sym_no_mac.json"),
            read_layers=False,
        )
        with patch("zmk_hid_daemon.switch_macime_layout") as switch:
            with patch("zmk_hid_daemon.trigger_sketchybar_update"):
                daemon._handle_report(bytes([0xAD, 2]))
                daemon._handle_report(bytes([0xAD, 3]))
        switch.assert_not_called()


MANUAL_LAYER_SWITCH_CHECKLIST = """
Manual test: base ↔ ru without garbage characters
=================================================

Prerequisites:
  - Both daemons running (install-zmk-daemons.sh)
  - Firmware reflashed after keymap change
  - macOS layout ABC before test
  - Focus empty TextEdit or this terminal

Steps:
  1. On base layer, type: hello
     Expected: hello (no extra symbols)

  2. Press layer_ru thumb key (base → ru)
     Expected: NO new character appears (especially not ")
     Expected: macOS input menu shows Russian

  3. Type: привет
     Expected: привет

  4. Press layer_en thumb key (ru → base)
     Expected: NO new character appears
     Expected: macOS input menu shows ABC

  5. Type: world
     Expected: world

  6. Repeat steps 2–5 five times quickly
     Expected: document stays clean — no ", !, № or other shortcut leaks

Log check:
  zmk-layer-daemon.log should show:
    Layer update ... ru (index 1)
    Keyboard layer 1 → Mac com.apple.keylayout.Russian
  zmk-mac-layout-daemon.log should NOT show Ctrl+Shift+2 on step 2
    (only sym `en` macro may trigger shortcuts, with consume_shortcuts=true)
"""


class TestManualChecklist(unittest.TestCase):
    def test_manual_checklist_present(self) -> None:
        self.assertIn('especially not "', MANUAL_LAYER_SWITCH_CHECKLIST)
        self.assertIn("layer_ru thumb", MANUAL_LAYER_SWITCH_CHECKLIST)


if __name__ == "__main__":
    if "--print-manual" in sys.argv:
        print(MANUAL_LAYER_SWITCH_CHECKLIST)
        sys.exit(0)
    unittest.main()
