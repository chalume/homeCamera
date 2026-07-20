#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/mac_usb_preview.sh [options]

Options:
  -d, --device DEVICE    AVFoundation video device name or index. Default: LumenPnP Bottom
  -s, --size WxH         Preview size. Default: 1280x720
  -r, --rate FPS         Framerate. Default: 30
  --pixel-format FORMAT  AVFoundation pixel format. Default: uyvy422
  --brightness VALUE     FFmpeg brightness, -1.0 to 1.0. Default: 0
  --contrast VALUE       FFmpeg contrast multiplier. Default: 1
  --gamma VALUE          FFmpeg gamma multiplier. Default: 1
  --saturation VALUE     FFmpeg saturation multiplier. Default: 1
  --help                 Show this help.

Examples:
  ./scripts/mac_usb_preview.sh
  ./scripts/mac_usb_preview.sh -d "LumenPnP Bottom" -s 1920x1080
  ./scripts/mac_usb_preview.sh --brightness -0.25 --contrast 1.15
USAGE
}

DEVICE="LumenPnP Bottom"
SIZE="1280x720"
RATE="30"
PIXEL_FORMAT="uyvy422"
BRIGHTNESS="0"
CONTRAST="1"
GAMMA="1"
SATURATION="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--device)
      DEVICE="${2:?Missing value for $1}"
      shift 2
      ;;
    -s|--size)
      SIZE="${2:?Missing value for $1}"
      shift 2
      ;;
    -r|--rate)
      RATE="${2:?Missing value for $1}"
      shift 2
      ;;
    --pixel-format)
      PIXEL_FORMAT="${2:?Missing value for $1}"
      shift 2
      ;;
    --brightness)
      BRIGHTNESS="${2:?Missing value for $1}"
      shift 2
      ;;
    --contrast)
      CONTRAST="${2:?Missing value for $1}"
      shift 2
      ;;
    --gamma)
      GAMMA="${2:?Missing value for $1}"
      shift 2
      ;;
    --saturation)
      SATURATION="${2:?Missing value for $1}"
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

BRIGHTNESS="${BRIGHTNESS/,/.}"
CONTRAST="${CONTRAST/,/.}"
GAMMA="${GAMMA/,/.}"
SATURATION="${SATURATION/,/.}"

ffplay \
  -hide_banner \
  -loglevel warning \
  -f avfoundation \
  -video_size "$SIZE" \
  -framerate "$RATE" \
  -pixel_format "$PIXEL_FORMAT" \
  -i "$DEVICE:none" \
  -vf "eq=brightness=${BRIGHTNESS}:contrast=${CONTRAST}:gamma=${GAMMA}:saturation=${SATURATION}"
