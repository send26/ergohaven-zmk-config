#!/usr/bin/env python3
"""Interactive manual test: layer switch must not type garbage (especially ")."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    print("=" * 60)
    print("Manual test: base ↔ ru layer switch")
    print("=" * 60)
    print()
    print("Before starting:")
    print("  • Reflash firmware if keymap changed")
    print("  • Restart daemons: ./scripts/install-zmk-daemons.sh")
    print("  • Open TextEdit with empty document, cursor at end")
    print("  • macOS layout = ABC (English)")
    print()
    input("Press Enter when TextEdit is focused and empty... ")
    print()
    print("Step 1: On BASE layer type exactly: hello")
    input("Done? Press Enter...")
    typed1 = input('Paste what appeared after "hello" (or Enter if nothing extra): ').strip()
    if typed1:
        print(f"  WARN: extra after hello: {typed1!r}")
    print()
    print("Step 2: Press LAYER_RU (base → ru). Do NOT type anything else.")
    input("Done? Press Enter...")
    leaked = input('Did a stray character appear (e.g. ")? Paste it or Enter if none: ').strip()
    if leaked:
        print(f"  FAIL: garbage on layer switch: {leaked!r}")
        return 1
    print("  OK: no garbage on ru switch")
    print()
    print("Step 3: Type: привет")
    input("Done? Press Enter...")
    print()
    print("Step 4: Press LAYER_EN (ru → base)")
    input("Done? Press Enter...")
    leaked2 = input("Stray character on en switch? Paste or Enter if none: ").strip()
    if leaked2:
        print(f"  FAIL: garbage on en switch: {leaked2!r}")
        return 1
    print("  OK: no garbage on en switch")
    print()
    print("Step 5: Repeat ru → en switch 3× quickly, watch for any symbol.")
    input("Done? Press Enter...")
    final = input("Any garbage accumulated? Paste all or Enter if clean: ").strip()
    if final:
        print(f"  FAIL: {final!r}")
        return 1
    print()
    print("PASS: layer switches clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
