#!/usr/bin/env bash
# Run daemon autotests (layer sync + mac layout shortcuts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/run_daemon_tests.sh"
