#!/usr/bin/env python3
"""Parse ZMK keymap layer names into layers.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_KEYMAP = Path(__file__).resolve().parents[1] / "config" / "velvet_v3_ui_ruen.keymap"
DEFAULT_OUTPUT = Path(__file__).with_name("layers.json")
DEFAULT_KEYBOARDS = Path(__file__).with_name("keyboards.json")
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

LAYER_START_RE = re.compile(r"^        ([A-Za-z_][A-Za-z0-9_]*)\s*\{\s*$", re.MULTILINE)
DISPLAY_NAME_RE = re.compile(r'display-name\s*=\s*"([^"]+)"')
LABEL_RE = re.compile(r'label\s*=\s*"([^"]+)"')


def extract_keymap_section(keymap_text: str) -> str:
    match = re.search(r"^\s*keymap\s*\{\s*$", keymap_text, re.MULTILINE)
    if match is None:
        raise ValueError("keymap block not found")

    start = match.end()
    depth = 1
    index = start

    while index < len(keymap_text) and depth:
        char = keymap_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1

    return keymap_text[start : index - 1]


def parse_keymap_layers(keymap_text: str) -> list[dict]:
    keymap_section = extract_keymap_section(keymap_text)
    layers: list[dict] = []

    for match in LAYER_START_RE.finditer(keymap_section):
        layer_id = match.group(1)
        block_start = match.end()
        depth = 1
        index = block_start

        while index < len(keymap_section) and depth:
            char = keymap_section[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1

        block = keymap_section[block_start : index - 1]
        display_match = DISPLAY_NAME_RE.search(block)
        label_match = LABEL_RE.search(block)

        if display_match:
            label = display_match.group(1)
        elif label_match:
            label = label_match.group(1)
        else:
            label = layer_id

        layers.append(
            {
                "index": len(layers),
                "id": layer_id,
                "label": label,
            }
        )

    return layers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Regenerate layers files for all keyboards in keyboards.json",
    )
    parser.add_argument(
        "-k",
        "--keymap",
        type=Path,
        default=DEFAULT_KEYMAP,
        help="Path to .keymap file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output JSON path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.all:
        if not DEFAULT_KEYBOARDS.exists():
            print(f"Keyboards config not found: {DEFAULT_KEYBOARDS}", file=sys.stderr)
            return 1

        keyboards = json.loads(DEFAULT_KEYBOARDS.read_text(encoding="utf-8"))
        scripts_dir = DEFAULT_KEYBOARDS.parent

        for keyboard_id, keyboard in keyboards.get("keyboards", {}).items():
            keymap_name = keyboard.get("keymap")
            layers_file = keyboard.get("layers_file")
            if not keymap_name or not layers_file:
                continue

            keymap_path = CONFIG_DIR / keymap_name
            output_path = scripts_dir / layers_file
            if not keymap_path.exists():
                print(f"Skipping {keyboard_id}: keymap not found at {keymap_path}", file=sys.stderr)
                continue

            layers = parse_keymap_layers(keymap_path.read_text(encoding="utf-8"))
            output_path.write_text(json.dumps(layers, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote {len(layers)} layers to {output_path}")

        return 0

    if not args.keymap.exists():
        print(f"Keymap not found: {args.keymap}", file=sys.stderr)
        return 1

    keymap_text = args.keymap.read_text(encoding="utf-8")
    layers = parse_keymap_layers(keymap_text)
    args.output.write_text(json.dumps(layers, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(layers)} layers to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
