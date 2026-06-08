#!/usr/bin/env bash
# Build ZMK firmware in Docker (same flow as ergohaven CI).
set -euo pipefail

# Docker Desktop credential helper lives here; /usr/local/bin/docker often lacks it in PATH.
DOCKER_DESKTOP_BIN="/Applications/Docker.app/Contents/Resources/bin"
if [[ -d "$DOCKER_DESKTOP_BIN" ]]; then
  export PATH="$DOCKER_DESKTOP_BIN:$PATH"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZMK_IMAGE="${ZMK_IMAGE:-zmkfirmware/zmk-build-arm:stable}"
WORKSPACE_DIR="${ZMK_WORKSPACE_DIR:-$REPO_ROOT/.zmk-workspace}"

BOARD="${BOARD:-ergohaven}"
SHIELD="${SHIELD:-velvet_v3_ui_qube qube dongle_screen raw_hid_adapter}"
KEYMAP="${KEYMAP:-velvet_v3_ui_ruen}"
SNIPPET="${SNIPPET:-studio-rpc-usb-uart}"
ARTIFACT_NAME="${ARTIFACT_NAME:-velvet_v3_ui_qube_ruen-ergohaven-zmk}"
CMAKE_ARGS="${CMAKE_ARGS:--DCONFIG_ZMK_STUDIO=y}"

BUILD_DIR="${BUILD_DIR:-$REPO_ROOT/build/$ARTIFACT_NAME}"
OUTPUT_UF2="${OUTPUT_UF2:-$REPO_ROOT/build/artifacts/$ARTIFACT_NAME.uf2}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --board NAME          ZMK board (default: ergohaven)
  --shield "SHIELDS"    Shield list (default: qube ruen target)
  --keymap NAME         Keymap base name without .keymap (default: velvet_v3_ui_ruen)
  --snippet NAME        West snippet (default: studio-rpc-usb-uart)
  --artifact NAME       Output uf2 base name (default: velvet_v3_ui_qube_ruen-ergohaven-zmk)
  --build-dir PATH      West build directory
  --output PATH         Where to copy the built .uf2 on the host
  --refresh             Force west update before build
  -h, --help            Show this help
EOF
}

REFRESH=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --board) BOARD="$2"; shift 2 ;;
    --shield) SHIELD="$2"; shift 2 ;;
    --keymap) KEYMAP="$2"; shift 2 ;;
    --snippet) SNIPPET="$2"; shift 2 ;;
    --artifact) ARTIFACT_NAME="$2"; shift 2 ;;
    --build-dir) BUILD_DIR="$2"; shift 2 ;;
    --output) OUTPUT_UF2="$2"; shift 2 ;;
    --refresh) REFRESH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not in PATH." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

mkdir -p "$WORKSPACE_DIR" "$BUILD_DIR" "$(dirname "$OUTPUT_UF2")"

echo "==> Pulling $ZMK_IMAGE"
docker pull "$ZMK_IMAGE"

echo "==> Building $ARTIFACT_NAME"
docker run --rm \
  -v "$REPO_ROOT:/workspace/user-config:ro" \
  -v "$WORKSPACE_DIR:/workspace/zmk-base" \
  -v "$BUILD_DIR:/workspace/build" \
  -v "$REPO_ROOT/build/artifacts:/workspace/artifacts" \
  -e BOARD="$BOARD" \
  -e SHIELD="$SHIELD" \
  -e KEYMAP="$KEYMAP" \
  -e SNIPPET="$SNIPPET" \
  -e ARTIFACT_NAME="$ARTIFACT_NAME" \
  -e CMAKE_ARGS="$CMAKE_ARGS" \
  -e REFRESH="$REFRESH" \
  "$ZMK_IMAGE" \
  bash -lc '
set -euo pipefail

rm -rf /workspace/zmk-base/config
mkdir -p /workspace/zmk-base/config
cp -a /workspace/user-config/config/. /workspace/zmk-base/config/

cd /workspace/zmk-base

if [[ ! -f .west/config ]]; then
  echo "==> west init"
  west init -l config
  west update
  west zephyr-export
elif [[ "$REFRESH" == "1" ]]; then
  echo "==> west update (refresh)"
  west update
  west zephyr-export
fi

KEYMAP_ARGS=()
if [[ -n "$KEYMAP" ]]; then
  KEYMAP_ARGS=(-DKEYMAP_FILE="/workspace/zmk-base/config/${KEYMAP}.keymap")
fi

SNIPPET_ARGS=()
if [[ -n "$SNIPPET" ]]; then
  SNIPPET_ARGS=(-S "$SNIPPET")
fi

west build -s zmk/app -d /workspace/build -b "$BOARD" "${SNIPPET_ARGS[@]}" -- \
  -DZMK_CONFIG=/workspace/zmk-base/config \
  "${KEYMAP_ARGS[@]}" \
  -DSHIELD="$SHIELD" \
  -DZMK_EXTRA_MODULES=/workspace/user-config \
  $CMAKE_ARGS

mkdir -p /workspace/artifacts
cp /workspace/build/zephyr/zmk.uf2 "/workspace/artifacts/${ARTIFACT_NAME}.uf2"
'

echo "==> Firmware ready: $OUTPUT_UF2"
ls -lh "$OUTPUT_UF2"
