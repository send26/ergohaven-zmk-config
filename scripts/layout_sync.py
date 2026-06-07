#!/usr/bin/env python3
"""Backward-compatible wrapper for macOS → keyboard layout sync."""

from __future__ import annotations

import sys

from zmk_hid_daemon import main

if __name__ == "__main__":
    if "--layout-only" not in sys.argv:
        sys.argv.insert(1, "--layout-only")
    sys.exit(main())
