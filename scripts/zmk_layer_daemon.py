#!/usr/bin/env python3
"""SketchyBar-facing entry point for the unified ZMK Raw HID daemon."""

from zmk_hid_daemon import main

if __name__ == "__main__":
    raise SystemExit(main())
