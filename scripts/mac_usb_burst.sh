#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/mac_usb_burst.sh [options]

Options:
  -d, --device DEVICE    AVFoundation video device name or index. Default: LumenPnP Bottom
  -n, --count NUMBER     Number of photos. Default: 5
  -i, --interval SEC     Delay between photos. Default: 2
  -s, --size WxH         Capture size. Default: 1280x720
  --help                 Show this help.
USAGE
}

DEVICE="LumenPnP Bottom"
COUNT="5"
INTERVAL="2"
SIZE="1280x720"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--device)
      DEVICE="${2:?Missing value for $1}"
      shift 2
      ;;
    -n|--count)
      COUNT="${2:?Missing value for $1}"
      shift 2
      ;;
    -i|--interval)
      INTERVAL="${2:?Missing value for $1}"
      shift 2
      ;;
    -s|--size)
      SIZE="${2:?Missing value for $1}"
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

for index in $(seq 1 "$COUNT"); do
  stamp="$(date +%Y%m%d-%H%M%S)"
  out="captures/mac-usb-burst-${stamp}-${index}.jpg"
  "$(dirname "$0")/mac_usb_capture.sh" -d "$DEVICE" -s "$SIZE" -o "$out"

  if [[ "$index" != "$COUNT" ]]; then
    sleep "$INTERVAL"
  fi
done
