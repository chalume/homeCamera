#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/capture_burst.sh [options]

Options:
  -n, --count NUMBER     Number of photos. Default: 5
  -i, --interval SEC     Delay between photos. Default: 2
  -d, --dir PATH         Output directory. Default: captures
  -w, --width PIXELS     Image width. Default: 1280
  -h, --height PIXELS    Image height. Default: 720
  -t, --timeout MS       Camera warm-up time per photo. Default: 1000
  --help                 Show this help.

Examples:
  ./scripts/capture_burst.sh
  ./scripts/capture_burst.sh -n 10 -i 1
  ./scripts/capture_burst.sh -d captures/cadrage -w 1920 -h 1080
USAGE
}

COUNT="5"
INTERVAL="2"
OUT_DIR="captures"
WIDTH="1280"
HEIGHT="720"
TIMEOUT="1000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--count)
      COUNT="${2:?Missing value for $1}"
      shift 2
      ;;
    -i|--interval)
      INTERVAL="${2:?Missing value for $1}"
      shift 2
      ;;
    -d|--dir)
      OUT_DIR="${2:?Missing value for $1}"
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

mkdir -p "$OUT_DIR"

for index in $(seq 1 "$COUNT"); do
  stamp="$(date +%Y%m%d-%H%M%S)"
  out="${OUT_DIR}/burst-${stamp}-${index}.jpg"
  rpicam-jpeg --timeout "$TIMEOUT" --width "$WIDTH" --height "$HEIGHT" -o "$out"
  echo "$out"

  if [[ "$index" != "$COUNT" ]]; then
    sleep "$INTERVAL"
  fi
done
