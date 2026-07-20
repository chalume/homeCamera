#!/usr/bin/env python3
"""Watch a Mac USB camera for motion, then capture a still image.

This intentionally avoids OpenCV so it can run with only Python and ffmpeg.
It reads a small grayscale stream, detects frame differences, and calls
mac_usb_capture.sh when motion is stable enough.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def parse_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must look like 320x180") from exc

    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size values must be positive")

    return width, height


def parse_float(value: str) -> float:
    return float(value.replace(",", "."))


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def mean_luma_pct(frame: bytes, sample_step: int) -> float:
    total = 0
    count = 0
    for index in range(0, len(frame), sample_step):
        total += frame[index]
        count += 1
    return (total / count / 255 * 100) if count else 0.0


def adjusted_luma_pct(raw_luma_pct: float, brightness: float) -> float:
    return clamp(raw_luma_pct + (brightness * 100), 0.0, 100.0)


def motion_score(
    frame: bytes,
    background: bytearray,
    pixel_delta: int,
    sample_step: int,
    normalize_luminance: bool,
) -> tuple[float, float]:
    changed = 0
    total = 0
    mean_shift = 0.0

    if normalize_luminance:
        shift_total = 0
        shift_count = 0
        for index in range(0, len(frame), sample_step):
            shift_total += frame[index] - background[index]
            shift_count += 1
        mean_shift = shift_total / shift_count if shift_count else 0.0

    for index in range(0, len(frame), sample_step):
        delta = (frame[index] - background[index]) - mean_shift
        if abs(delta) >= pixel_delta:
            changed += 1
        total += 1

    return (changed / total if total else 0.0), mean_shift


def update_background(background: bytearray, frame: bytes, alpha_percent: int) -> None:
    keep = 100 - alpha_percent
    for index, value in enumerate(frame):
        background[index] = ((background[index] * keep) + (value * alpha_percent)) // 100


def start_monitor_stream(
    device: str,
    input_size: str,
    monitor_size: tuple[int, int],
    rate: int,
    pixel_format: str,
) -> subprocess.Popen[bytes]:
    width, height = monitor_size
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "avfoundation",
        "-video_size",
        input_size,
        "-framerate",
        str(rate),
        "-pixel_format",
        pixel_format,
        "-i",
        f"{device}:none",
        "-vf",
        f"scale={width}:{height},format=gray",
        "-f",
        "rawvideo",
        "pipe:1",
    ]

    return subprocess.Popen(command, stdout=subprocess.PIPE)


def stop_monitor_stream(process: subprocess.Popen[bytes], timeout: float = 3.0) -> None:
    if process.stdout is not None:
        process.stdout.close()

    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def capture_media(
    script_dir: Path,
    capture_kind: str,
    device: str,
    capture_size: str,
    rate: int,
    video_duration: float,
    output_dir: Path,
    brightness: str,
    contrast: str,
    gamma: str,
    saturation: str,
    discord: bool,
    message: str,
) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = "mp4" if capture_kind == "video" else "jpg"
    output_path = output_dir / f"motion-{stamp}.{suffix}"
    capture_script = (
        script_dir / "mac_usb_capture_video.sh"
        if capture_kind == "video"
        else script_dir / "mac_usb_capture.sh"
    )
    command = [
        str(capture_script),
        "-d",
        device,
        "-s",
        capture_size,
        "-r",
        str(rate),
        "-o",
        str(output_path),
        "--brightness",
        brightness,
        "--contrast",
        contrast,
        "--gamma",
        gamma,
        "--saturation",
        saturation,
    ]

    if capture_kind == "video":
        command.extend(["--duration", str(video_duration)])

    subprocess.run(command, check=True)

    if discord:
        subprocess.run(
            [
                sys.executable,
                str(script_dir / "send_discord_photo.py"),
                str(output_path),
                "--message",
                message,
            ],
            check=True,
        )

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--device",
        default="LumenPnP Bottom",
        help="AVFoundation video device name or index.",
    )
    parser.add_argument(
        "--input-size",
        default="1280x720",
        help="Camera mode used by ffmpeg. Must be supported by the camera.",
    )
    parser.add_argument(
        "--capture-size",
        default="1920x1080",
        help="Media capture size after motion is detected.",
    )
    parser.add_argument(
        "--capture-kind",
        choices=("photo", "video"),
        default="photo",
        help="Capture a still photo or a short video after motion is detected.",
    )
    parser.add_argument(
        "--video-duration",
        default=5.0,
        type=float,
        help="Video duration in seconds when --capture-kind video is used.",
    )
    parser.add_argument(
        "--monitor-size",
        default="320x180",
        type=parse_size,
        help="Low-resolution grayscale size used for motion detection.",
    )
    parser.add_argument("-r", "--rate", default=30, type=int, help="Monitoring FPS.")
    parser.add_argument(
        "--pixel-format",
        default="uyvy422",
        help="AVFoundation pixel format.",
    )
    parser.add_argument(
        "--capture-rate",
        default=30,
        type=int,
        help="FPS requested for the still capture.",
    )
    parser.add_argument(
        "--threshold",
        default=0.025,
        type=float,
        help="Changed-pixel ratio needed to count as motion.",
    )
    parser.add_argument(
        "--pixel-delta",
        default=28,
        type=int,
        help="Brightness difference needed for one pixel to count as changed.",
    )
    parser.add_argument(
        "--consecutive",
        default=3,
        type=int,
        help="Consecutive motion frames required before capture.",
    )
    parser.add_argument(
        "--background-alpha",
        default=3,
        type=int,
        help="Background adaptation percent per frame.",
    )
    parser.add_argument(
        "--no-luminance-normalize",
        action="store_true",
        help="Disable compensation for global brightness shifts.",
    )
    parser.add_argument(
        "--cooldown",
        default=30,
        type=float,
        help="Seconds to wait after a capture before triggering again.",
    )
    parser.add_argument(
        "--output-dir",
        default="captures",
        type=Path,
        help="Directory for motion captures.",
    )
    parser.add_argument(
        "--brightness",
        default="0",
        help="FFmpeg capture brightness, -1.0 to 1.0.",
    )
    parser.add_argument(
        "--auto-brightness",
        action="store_true",
        help="Adjust capture brightness automatically from measured luminance.",
    )
    parser.add_argument(
        "--target-luma",
        default=31.4,
        type=float,
        help="Target mean luminance percent for automatic brightness.",
    )
    parser.add_argument(
        "--brightness-check-interval",
        default=600,
        type=float,
        help="Seconds between automatic brightness adjustments.",
    )
    parser.add_argument(
        "--brightness-min",
        default=-0.5,
        type=float,
        help="Minimum automatic brightness value.",
    )
    parser.add_argument(
        "--brightness-max",
        default=0.5,
        type=float,
        help="Maximum automatic brightness value.",
    )
    parser.add_argument(
        "--brightness-gain",
        default=1.0,
        type=float,
        help="Automatic brightness correction gain.",
    )
    parser.add_argument(
        "--contrast",
        default="1",
        help="FFmpeg capture contrast multiplier.",
    )
    parser.add_argument(
        "--gamma",
        default="1",
        help="FFmpeg capture gamma multiplier.",
    )
    parser.add_argument(
        "--saturation",
        default="1",
        help="FFmpeg capture saturation multiplier.",
    )
    parser.add_argument(
        "--discord",
        action="store_true",
        help="Send captured photos to Discord using DISCORD_WEBHOOK_URL.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print motion score updates once per second.",
    )
    parser.add_argument(
        "--force-capture",
        action="store_true",
        help="Capture one photo immediately, then continue watching.",
    )
    parser.add_argument(
        "--message",
        default="Mouvement detecte dans le garage.",
        help="Discord message.",
    )
    args = parser.parse_args()

    if args.discord and not os.environ.get("DISCORD_WEBHOOK_URL"):
        print("DISCORD_WEBHOOK_URL must be set when --discord is used.", file=sys.stderr)
        return 2

    script_dir = Path(__file__).resolve().parent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame_len = args.monitor_size[0] * args.monitor_size[1]
    sample_step = max(1, frame_len // 12000)

    print("Starting motion watch.")
    print(f"Device: {args.device}")
    print(f"Monitor: {args.input_size}@{args.rate} -> {args.monitor_size[0]}x{args.monitor_size[1]}")
    print(
        f"Capture: {args.capture_kind}, device {args.device}, "
        f"{args.capture_size}@{args.capture_rate}"
    )
    if args.auto_brightness:
        print(
            "Auto brightness enabled: "
            f"target={args.target_luma:.1f}% "
            f"interval={args.brightness_check_interval:.0f}s"
        )
    print("Press Ctrl+C to stop.")

    process = start_monitor_stream(
        args.device,
        args.input_size,
        args.monitor_size,
        args.rate,
        args.pixel_format,
    )

    def stop_process(_signum: int, _frame: object) -> None:
        stop_monitor_stream(process)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop_process)
    signal.signal(signal.SIGTERM, stop_process)

    background: bytearray | None = None
    motion_frames = 0
    last_capture_at = 0.0
    last_debug_at = 0.0
    best_debug_score = 0.0
    current_brightness = parse_float(args.brightness)
    last_brightness_check_at = 0.0
    current_luma_pct = 0.0
    current_adjusted_luma_pct = 0.0

    try:
        assert process.stdout is not None

        if args.force_capture:
            print("Force capture requested.")
            stop_monitor_stream(process)
            output_path = capture_media(
                script_dir,
                args.capture_kind,
                args.device,
                args.capture_size,
                args.capture_rate,
                args.video_duration,
                args.output_dir,
                f"{current_brightness:.3f}",
                args.contrast,
                args.gamma,
                args.saturation,
                args.discord,
                args.message,
            )
            print(output_path)
            process = start_monitor_stream(
                args.device,
                args.input_size,
                args.monitor_size,
                args.rate,
                args.pixel_format,
            )
            assert process.stdout is not None

        while True:
            frame = process.stdout.read(frame_len)
            if not frame:
                print("ffmpeg stream ended.", file=sys.stderr)
                return process.wait() or 1
            if len(frame) != frame_len:
                print("Incomplete frame received.", file=sys.stderr)
                return 1

            if background is None:
                background = bytearray(frame)
                continue

            current_luma_pct = mean_luma_pct(frame, sample_step)
            current_adjusted_luma_pct = adjusted_luma_pct(
                current_luma_pct,
                current_brightness,
            )
            now = time.monotonic()
            should_update_brightness = (
                args.auto_brightness
                and now - last_brightness_check_at >= args.brightness_check_interval
            )
            if should_update_brightness:
                correction = (args.target_luma - current_luma_pct) / 100 * args.brightness_gain
                current_brightness = clamp(
                    correction,
                    args.brightness_min,
                    args.brightness_max,
                )
                current_adjusted_luma_pct = adjusted_luma_pct(
                    current_luma_pct,
                    current_brightness,
                )
                last_brightness_check_at = now
                print(
                    "Auto brightness: "
                    f"raw_luma={current_luma_pct:.1f}% "
                    f"target={args.target_luma:.1f}% "
                    f"brightness={current_brightness:.3f} "
                    f"adjusted_luma={current_adjusted_luma_pct:.1f}%"
                )

            score, mean_shift = motion_score(
                frame,
                background,
                args.pixel_delta,
                sample_step,
                normalize_luminance=not args.no_luminance_normalize,
            )
            update_background(background, frame, alpha_percent=args.background_alpha)
            best_debug_score = max(best_debug_score, score)

            if score >= args.threshold:
                motion_frames += 1
            else:
                motion_frames = 0

            cooldown_remaining = max(0.0, args.cooldown - (now - last_capture_at))
            if args.debug and now - last_debug_at >= 1.0:
                print(
                    "score="
                    f"{score:.4f} best={best_debug_score:.4f} "
                    f"threshold={args.threshold:.4f} "
                    f"mean_shift={mean_shift:.1f} "
                    f"raw_luma={current_luma_pct:.1f}% "
                    f"adjusted_luma={current_adjusted_luma_pct:.1f}% "
                    f"brightness={current_brightness:.3f} "
                    f"motion_frames={motion_frames}/{args.consecutive} "
                    f"cooldown_remaining={cooldown_remaining:.1f}s"
                )
                last_debug_at = now
                best_debug_score = 0.0

            can_capture = cooldown_remaining <= 0.0
            if motion_frames >= args.consecutive and can_capture:
                print(f"Motion detected: score={score:.3f}")
                stop_monitor_stream(process)
                time.sleep(0.5)

                output_path = capture_media(
                    script_dir,
                    args.capture_kind,
                    args.device,
                    args.capture_size,
                    args.capture_rate,
                    args.video_duration,
                    args.output_dir,
                    f"{current_brightness:.3f}",
                    args.contrast,
                    args.gamma,
                    args.saturation,
                    args.discord,
                    args.message,
                )
                print(output_path)
                last_capture_at = now
                motion_frames = 0
                background = None

                process = start_monitor_stream(
                    args.device,
                    args.input_size,
                    args.monitor_size,
                    args.rate,
                    args.pixel_format,
                )
                assert process.stdout is not None

    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        stop_monitor_stream(process)


if __name__ == "__main__":
    raise SystemExit(main())
