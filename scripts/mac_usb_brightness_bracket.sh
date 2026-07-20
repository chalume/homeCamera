#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/mac_usb_brightness_bracket.sh [options]

Options:
  -d, --device DEVICE    AVFoundation video device name or index. Default: LumenPnP Bottom
  -s, --size WxH         Capture size. Default: 1280x720
  -r, --rate FPS         Framerate requested from camera. Default: 30
  --pixel-format FORMAT  AVFoundation pixel format. Default: uyvy422
  --start VALUE          First brightness value. Default: -0.50
  --step VALUE           Brightness step. Default: 0.10
  -n, --count NUMBER     Number of captures. Default: 11
  --contrast VALUE       FFmpeg contrast multiplier. Default: 1
  --gamma VALUE          FFmpeg gamma multiplier. Default: 1
  --saturation VALUE     FFmpeg saturation multiplier. Default: 1
  --dir PATH             Output directory. Default: captures/brightness-test-YYYYmmdd-HHMMSS
  --help                 Show this help.

Examples:
  ./scripts/mac_usb_brightness_bracket.sh
  ./scripts/mac_usb_brightness_bracket.sh --start -0.40 --step 0.10 -n 9
  ./scripts/mac_usb_brightness_bracket.sh --contrast 1.15 --gamma 0.85
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEVICE="LumenPnP Bottom"
SIZE="1280x720"
RATE="30"
PIXEL_FORMAT="uyvy422"
START="-0.50"
STEP="0.10"
COUNT="11"
CONTRAST="1"
GAMMA="1"
SATURATION="1"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="captures/brightness-test-${STAMP}"

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
    --start)
      START="${2:?Missing value for $1}"
      shift 2
      ;;
    --step)
      STEP="${2:?Missing value for $1}"
      shift 2
      ;;
    -n|--count)
      COUNT="${2:?Missing value for $1}"
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
    --dir)
      OUT_DIR="${2:?Missing value for $1}"
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

START="${START/,/.}"
STEP="${STEP/,/.}"
CONTRAST="${CONTRAST/,/.}"
GAMMA="${GAMMA/,/.}"
SATURATION="${SATURATION/,/.}"

mkdir -p "$OUT_DIR"
CSV="$OUT_DIR/brightness_report.csv"
echo "index,brightness,mean_luma_pct,mean_luma_0_255,path" > "$CSV"

for index in $(seq 0 "$((COUNT - 1))"); do
  brightness="$(LC_ALL=C awk -v start="$START" -v step="$STEP" -v i="$index" 'BEGIN { printf "%.3f", start + (step * i) }')"
  safe_brightness="${brightness/-/m}"
  safe_brightness="${safe_brightness/./p}"
  safe_brightness="${safe_brightness/,/p}"
  out="$OUT_DIR/brightness-${safe_brightness}.jpg"

  "$SCRIPT_DIR/mac_usb_capture.sh" \
    -d "$DEVICE" \
    -s "$SIZE" \
    -r "$RATE" \
    --pixel-format "$PIXEL_FORMAT" \
    --brightness "$brightness" \
    --contrast "$CONTRAST" \
    --gamma "$GAMMA" \
    --saturation "$SATURATION" \
    -o "$out" >/dev/null

  mean_pct="$(
    ffmpeg -hide_banner -i "$out" -vf "format=gray,signalstats,metadata=print:file=-" -frames:v 1 -f null - 2>/dev/null \
      | awk -F= '/lavfi.signalstats.YAVG=/ { printf "%.4f", $2 / 255 * 100 }'
  )"
  mean_255="$(LC_ALL=C awk -v pct="$mean_pct" 'BEGIN { printf "%.2f", pct * 255 / 100 }')"

  echo "${index},${brightness},${mean_pct},${mean_255},${out}" >> "$CSV"
  printf "%2d  brightness=%7s  mean=%7s%%  %s\n" "$index" "$brightness" "$mean_pct" "$out"
done

echo
echo "$CSV"
