#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/pi_usb_capture.sh [options]

Options:
  -d, --device PATH      V4L2 video device. Default: /dev/video0
  -o, --output PATH      Output image path. Default: captures/pi-usb-YYYYmmdd-HHMMSS.jpg
  -s, --size WxH         Capture size. Default: 1280x720
  -r, --rate FPS         Framerate. Default: 30
  --warmup-frames N      Frames to discard before saving. Default: 1
  --input-format FORMAT  V4L2 input format. Default: mjpeg
  --brightness VALUE     FFmpeg brightness, -1.0 to 1.0. Default: 0
  --contrast VALUE       FFmpeg contrast multiplier. Default: 1
  --gamma VALUE          FFmpeg gamma multiplier. Default: 1
  --saturation VALUE     FFmpeg saturation multiplier. Default: 1
  --help                 Show this help.
USAGE
}

DEVICE="/dev/video0"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="captures/pi-usb-${STAMP}.jpg"
SIZE="1280x720"
RATE="30"
WARMUP_FRAMES="1"
INPUT_FORMAT="mjpeg"
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
    -o|--output)
      OUT="${2:?Missing value for $1}"
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
    --warmup-frames)
      WARMUP_FRAMES="${2:?Missing value for $1}"
      shift 2
      ;;
    --input-format)
      INPUT_FORMAT="${2:?Missing value for $1}"
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

mkdir -p "$(dirname "$OUT")"

ffmpeg \
  -hide_banner \
  -loglevel warning \
  -f v4l2 \
  -input_format "$INPUT_FORMAT" \
  -video_size "$SIZE" \
  -framerate "$RATE" \
  -i "$DEVICE" \
  -vf "select='gte(n,${WARMUP_FRAMES})',eq=brightness=${BRIGHTNESS}:contrast=${CONTRAST}:gamma=${GAMMA}:saturation=${SATURATION}" \
  -vsync vfr \
  -frames:v 1 \
  -update 1 \
  -y "$OUT"

echo "$OUT"
