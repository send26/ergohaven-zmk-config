#!/usr/bin/env bash
# Install or reload ZMK LaunchAgents (layer sync + mac layout shortcuts).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
AGENTS_DIR="${HOME}/Library/LaunchAgents"

install_agent() {
  local label="$1"
  local plist_src="$2"
  local plist_dst="${AGENTS_DIR}/${label}.plist"

  mkdir -p "$AGENTS_DIR"
  cp "$plist_src" "$plist_dst"
  chmod 644 "$plist_dst"

  # bootout is fine if not loaded
  launchctl bootout "${DOMAIN}/${label}" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$plist_dst"
  launchctl enable "${DOMAIN}/${label}" 2>/dev/null || true
  launchctl kickstart -k "${DOMAIN}/${label}"
  echo "OK: ${label}"
}

echo "Installing LaunchAgents from ${ROOT}/scripts ..."
install_agent "com.senders.zmk-layer-daemon" \
  "${ROOT}/scripts/com.senders.zmk-layer-daemon.plist"
install_agent "com.senders.zmk-mac-layout-daemon" \
  "${ROOT}/scripts/com.senders.zmk-mac-layout-daemon.plist"

echo ""
echo "Status:"
launchctl print "${DOMAIN}/com.senders.zmk-layer-daemon" 2>&1 | rg 'state =|last exit code' || true
launchctl print "${DOMAIN}/com.senders.zmk-mac-layout-daemon" 2>&1 | rg 'state =|last exit code' || true
echo ""
echo "Logs:"
echo "  ~/Library/Logs/zmk-layer-daemon.log"
echo "  ~/Library/Logs/zmk-mac-layout-daemon.log"
echo ""
echo "Note: launchctl load is deprecated. Use this script or:"
echo "  launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/<label>.plist"
echo ""
echo "Mac layout daemon needs Accessibility for python3 (CGEventTap):"
echo "  System Settings → Privacy & Security → Accessibility → add /usr/local/bin/python3"
