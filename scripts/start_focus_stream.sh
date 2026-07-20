#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/start_focus_stream.sh [options]

Options:
  -p, --port PORT        TCP port. Default: 8888
  -w, --width PIXELS     Video width. Default: 1280
  -h, --height PIXELS    Video height. Default: 720
  -f, --framerate FPS    Framerate. Default: 15
  --help                 Show this help.

Open the stream from another computer with VLC:
  tcp/h264://chalume.local:8888
USAGE
}

PORT="8888"
WIDTH="1280"
HEIGHT="720"
FRAMERATE="15"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)
      PORT="${2:?Missing value for $1}"
      shift 2
      ;;
    -w|--width)
      WIDTH="${2:?Missing value for $1}"
      shift 2
      ;;
    -h|--height)
      HEIGHT="${2:?Missing value for $1}"
      shift 2
      ;;
    -f|--framerate)
      FRAMERATE="${2:?Missing value for $1}"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

echo "Starting focus stream on tcp/h264://chalume.local:${PORT}"
echo "Press Ctrl+C to stop."

rpicam-vid \
  --timeout 0 \
  --width "$WIDTH" \
  --height "$HEIGHT" \
  --framerate "$FRAMERATE" \
  --codec h264 \
  --inline \
  --listen \
  -o "tcp://0.0.0.0:${PORT}"
