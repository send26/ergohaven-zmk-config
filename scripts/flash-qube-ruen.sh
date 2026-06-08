#!/usr/bin/env bash
# Build velvet qube ruen firmware and copy it to the nRF52 USB bootloader volume.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BOOT_MOUNT="${NRF52_BOOT_MOUNT:-/Volumes/NRF52BOOT}"
ARTIFACT_NAME="velvet_v3_ui_qube_ruen-ergohaven-zmk"
OUTPUT_UF2="$REPO_ROOT/build/artifacts/$ARTIFACT_NAME.uf2"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"
BUILD_ONLY=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Build velvet_v3_ui_qube_ruen firmware in Docker and copy the .uf2 to NRF52BOOT.

Workflow:
  1. Edit config in $REPO_ROOT/config/
  2. Put qube into bootloader mode (double-tap reset) so NRF52BOOT appears
  3. Run this script

Options:
  --build-only          Build firmware but do not copy to NRF52BOOT
  --no-wait             Fail immediately if NRF52BOOT is not mounted
  --wait SECONDS        Wait for NRF52BOOT (default: $WAIT_TIMEOUT)
  -h, --help            Show this help
EOF
}

NO_WAIT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-only) BUILD_ONLY=1; shift ;;
    --no-wait) NO_WAIT=1; shift ;;
    --wait) WAIT_TIMEOUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

wait_for_bootloader() {
  if [[ -d "$BOOT_MOUNT" ]]; then
    return 0
  fi

  if [[ "$NO_WAIT" == "1" ]]; then
    echo "Bootloader volume not found: $BOOT_MOUNT" >&2
    echo "Put qube in bootloader mode (double-tap reset) and rerun." >&2
    return 1
  fi

  echo "Waiting for $BOOT_MOUNT (put qube in bootloader mode)..."
  local elapsed=0
  while [[ ! -d "$BOOT_MOUNT" ]]; do
    if (( elapsed >= WAIT_TIMEOUT )); then
      echo "Timed out after ${WAIT_TIMEOUT}s waiting for $BOOT_MOUNT." >&2
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
}

echo "==> Building firmware"
"$SCRIPT_DIR/zmk-docker-build.sh" \
  --artifact "$ARTIFACT_NAME" \
  --output "$OUTPUT_UF2"

if [[ "$BUILD_ONLY" == "1" ]]; then
  echo "Build finished. Skipping flash (--build-only)."
  exit 0
fi

wait_for_bootloader

DEST="$BOOT_MOUNT/$ARTIFACT_NAME.uf2"
echo "==> Copying firmware to $DEST"
cp "$OUTPUT_UF2" "$DEST"
sync

echo "Done. Qube should reboot with the new firmware shortly."
