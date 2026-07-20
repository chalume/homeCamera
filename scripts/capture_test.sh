#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/capture_test.sh [options]

Options:
  -o, --output PATH      Output image path. Default: captures/test-YYYYmmdd-HHMMSS.jpg
  -w, --width PIXELS     Image width. Default: 1280
  -h, --height PIXELS    Image height. Default: 720
  -t, --timeout MS       Camera warm-up time. Default: 1500
  --help                 Show this help.

Examples:
  ./scripts/capture_test.sh
  ./scripts/capture_test.sh -o captures/gamelle.jpg
  ./scripts/capture_test.sh -w 1920 -h 1080 -t 2500
USAGE
}

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="captures/test-${STAMP}.jpg"
WIDTH="1280"
HEIGHT="720"
TIMEOUT="1500"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output)
      OUT="${2:?Missing value for $1}"
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
    -t|--timeout)
      TIMEOUT="${2:?Missing value for $1}"
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

mkdir -p "$(dirname "$OUT")"
rpicam-jpeg --timeout "$TIMEOUT" --width "$WIDTH" --height "$HEIGHT" -o "$OUT"

echo "$OUT"
