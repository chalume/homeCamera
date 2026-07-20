#!/usr/bin/env bash
set -euo pipefail

LABEL="com.homecamera.motion-watch"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/${LABEL}.plist"
LOG_DIR="$REPO_DIR/logs"

case "$REPO_DIR" in
  "$HOME/Documents/"*|"$HOME/Desktop/"*|"$HOME/Downloads/"*)
    cat >&2 <<MESSAGE
This project is currently under a macOS privacy-protected folder:
  ${REPO_DIR}

launchd may not be allowed to execute scripts from Documents, Desktop, or
Downloads. Move or copy the project to a less restricted folder, for example:
  ${HOME}/homeCamera

Then run this installer again from the new location.
MESSAGE
    exit 2
    ;;
esac

mkdir -p "$PLIST_DIR" "$LOG_DIR"
chmod +x "$REPO_DIR/scripts/run_mac_usb_motion_watch.sh"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${REPO_DIR}/scripts/run_mac_usb_motion_watch.sh</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/motion-watch.out.log</string>

  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/motion-watch.err.log</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
launchctl start "$LABEL" 2>/dev/null || true

echo "$PLIST_PATH"
echo "Installed and started ${LABEL}"
echo "Logs:"
echo "  ${LOG_DIR}/motion-watch.out.log"
echo "  ${LOG_DIR}/motion-watch.err.log"
