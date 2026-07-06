#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/lib/python3.14/site-packages:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"

echo "=== layer switch tests (no garbage on ru/en) ==="
/usr/local/bin/python3 "$ROOT/scripts/test_layer_switch.py" -v

echo "=== layer sync tests ==="
/usr/local/bin/python3 "$ROOT/scripts/test_zmk_layer_sync.py" -v

echo "=== mac layout shortcut tests ==="
/usr/local/bin/python3 "$ROOT/scripts/test_zmk_mac_layout_daemon.py" -v
