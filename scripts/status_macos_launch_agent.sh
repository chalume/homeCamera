#!/usr/bin/env bash
set -euo pipefail

LABEL="com.homecamera.motion-watch"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

launchctl list "$LABEL" 2>/dev/null || {
  echo "${LABEL} is not loaded"
  exit 1
}

echo
echo "Recent stdout:"
tail -n 30 "$REPO_DIR/logs/motion-watch.out.log" 2>/dev/null || true

echo
echo "Recent stderr:"
tail -n 30 "$REPO_DIR/logs/motion-watch.err.log" 2>/dev/null || true
