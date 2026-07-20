#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${1:-captures/cat-${STAMP}.jpg}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

"$SCRIPT_DIR/capture_test.sh" "$REPO_DIR/$OUT"
python3 "$SCRIPT_DIR/send_discord_photo.py" "$REPO_DIR/$OUT"
