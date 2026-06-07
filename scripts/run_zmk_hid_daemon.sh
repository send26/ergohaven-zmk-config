#!/bin/bash

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/lib/python3.14/site-packages:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/local/bin/python3 "$ROOT/scripts/zmk_hid_daemon.py" "$@"
