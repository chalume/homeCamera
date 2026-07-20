#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"

cd "$REPO_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

exec "$REPO_DIR/scripts/mac_usb_motion_watch.py" \
  --discord \
  -d "LumenPnP Bottom" \
  --threshold 0.005 \
  --pixel-delta 40 \
  --consecutive 1 \
  --cooldown 30 \
  --capture-kind video \
  --video-duration 5 \
  --capture-size 1280x720 \
  --capture-rate 30 \
  --auto-brightness \
  --target-luma 31.4 \
  --brightness-check-interval 600
