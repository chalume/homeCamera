#!/usr/bin/env python3
"""Watch a Raspberry Pi USB/V4L2 camera for motion, then capture media."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import tempfile
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


def mean_luma_pct(frame: bytes, sample_step: int) -> float:
    total = 0
    count = 0
    for index in range(0, len(frame), sample_step):
        total += frame[index]
        count += 1
    return (total / count / 255 * 100) if count else 0.0


def set_camera_controls(
    device: str,
    auto_exposure: str | None,
    exposure_time: int | None,
    gain: int | None,
    camera_brightness: int | None,
    white_balance_auto: str | None,
    white_balance_temperature: int | None,
    backlight_compensation: int | None,
) -> None:
    controls: list[str] = []
    if auto_exposure is not None:
        controls.append(f"auto_exposure={auto_exposure}")
    if exposure_time is not None:
        controls.append(f"exposure_time_absolute={exposure_time}")
    if gain is not None:
        controls.append(f"gain={gain}")
    if camera_brightness is not None:
        controls.append(f"brightness={camera_brightness}")
    if white_balance_auto is not None:
        controls.append(f"white_balance_automatic={white_balance_auto}")
    if white_balance_temperature is not None:
        controls.append(f"white_balance_temperature={white_balance_temperature}")
    if backlight_compensation is not None:
        controls.append(f"backlight_compensation={backlight_compensation}")

    if not controls:
        return

    subprocess.run(
        [
            "v4l2-ctl",
            "-d",
            device,
            f"--set-ctrl={','.join(controls)}",
        ],
        check=True,
    )


def start_monitor_stream(
    device: str,
    input_format: str,
    input_size: str,
    monitor_size: tuple[int, int],
    rate: int,
    brightness: str,
    contrast: str,
    gamma: str,
    saturation: str,
) -> subprocess.Popen[bytes]:
    width, height = monitor_size
    video_filter = (
        f"eq=brightness={brightness}:contrast={contrast}:gamma={gamma}:saturation={saturation},"
        f"scale={width}:{height},format=gray"
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "v4l2",
        "-input_format",
        input_format,
        "-video_size",
        input_size,
        "-framerate",
        str(rate),
        "-i",
        device,
        "-vf",
        video_filter,
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


def capture_snapshot_frame(
    script_dir: Path,
    device: str,
    input_format: str,
    input_size: str,
    rate: int,
    monitor_size: tuple[int, int],
    brightness: str,
    contrast: str,
    gamma: str,
    saturation: str,
    temp_dir: Path,
) -> bytes:
    temp_jpg = temp_dir / "monitor.jpg"
    subprocess.run(
        [
            str(script_dir / "pi_usb_capture.sh"),
            "-d",
            device,
            "-s",
            input_size,
            "-r",
            str(rate),
            "--input-format",
            input_format,
            "-o",
            str(temp_jpg),
            "--brightness",
            brightness,
            "--contrast",
            contrast,
            "--gamma",
            gamma,
            "--saturation",
            saturation,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )

    width, height = monitor_size
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(temp_jpg),
            "-vf",
            f"scale={width}:{height},format=gray",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def capture_media(
    script_dir: Path,
    capture_kind: str,
    device: str,
    input_format: str,
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
        script_dir / "pi_usb_capture_video.sh"
        if capture_kind == "video"
        else script_dir / "pi_usb_capture.sh"
    )

    command = [
        str(capture_script),
        "-d",
        device,
        "-s",
        capture_size,
        "-r",
        str(rate),
        "--input-format",
        input_format,
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
    parser.add_argument("-d", "--device", default="/dev/video0")
    parser.add_argument("--input-format", default="mjpeg")
    parser.add_argument("--input-size", default="640x480")
    parser.add_argument("--monitor-mode", choices=("snapshot", "stream"), default="snapshot")
    parser.add_argument("--snapshot-interval", default=1.0, type=float)
    parser.add_argument("--capture-input-format", default="mjpeg")
    parser.add_argument("--capture-size", default="1280x720")
    parser.add_argument("--capture-kind", choices=("photo", "video"), default="video")
    parser.add_argument("--video-duration", default=5.0, type=float)
    parser.add_argument("--monitor-size", default="320x180", type=parse_size)
    parser.add_argument("-r", "--rate", default=30, type=int)
    parser.add_argument("--capture-rate", default=30, type=int)
    parser.add_argument("--threshold", default=0.005, type=float)
    parser.add_argument("--pixel-delta", default=40, type=int)
    parser.add_argument("--consecutive", default=1, type=int)
    parser.add_argument(
        "--simple",
        default=True,
        action="store_true",
        help="Use Mac-like detection loop: no arming, only settle time and cooldown.",
    )
    parser.add_argument(
        "--advanced-arm",
        dest="simple",
        action="store_false",
        help="Use the experimental quiet-frame arming logic.",
    )
    parser.add_argument(
        "--settle-seconds",
        default=5.0,
        type=float,
        help="Seconds to ignore motion while exposure/background stabilizes.",
    )
    parser.add_argument(
        "--arm-after-quiet-frames",
        default=0,
        type=int,
        help="Quiet frames required before motion detection is armed. Default: 0",
    )
    parser.add_argument("--background-alpha", default=3, type=int)
    parser.add_argument("--no-luminance-normalize", action="store_true")
    parser.add_argument("--cooldown", default=30, type=float)
    parser.add_argument("--output-dir", default="captures", type=Path)
    parser.add_argument("--brightness", default="0")
    parser.add_argument("--contrast", default="1")
    parser.add_argument("--gamma", default="1")
    parser.add_argument("--saturation", default="1")
    parser.add_argument(
        "--auto-exposure",
        choices=("manual", "auto"),
        help="V4L2 exposure mode. manual=1, auto=3 on this UVC camera.",
    )
    parser.add_argument("--exposure-time", type=int, help="V4L2 exposure_time_absolute value.")
    parser.add_argument("--gain", type=int, help="V4L2 gain value.")
    parser.add_argument("--camera-brightness", type=int, help="V4L2 hardware brightness value.")
    parser.add_argument(
        "--white-balance-auto",
        choices=("off", "on"),
        help="V4L2 automatic white balance.",
    )
    parser.add_argument("--white-balance-temperature", type=int)
    parser.add_argument("--backlight-compensation", type=int)
    parser.add_argument("--discord", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--force-capture", action="store_true")
    parser.add_argument(
        "--dump-monitor-frame",
        type=Path,
        help="Write one monitor frame as a grayscale PGM image, then exit.",
    )
    parser.add_argument("--message", default="Mouvement detecte dans le garage.")
    args = parser.parse_args()

    if args.discord and not os.environ.get("DISCORD_WEBHOOK_URL"):
        print("DISCORD_WEBHOOK_URL must be set when --discord is used.", file=sys.stderr)
        return 2

    script_dir = Path(__file__).resolve().parent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame_len = args.monitor_size[0] * args.monitor_size[1]
    sample_step = max(1, frame_len // 12000)
    auto_exposure_value = None
    if args.auto_exposure == "manual":
        auto_exposure_value = "1"
    elif args.auto_exposure == "auto":
        auto_exposure_value = "3"
    white_balance_auto_value = None
    if args.white_balance_auto == "off":
        white_balance_auto_value = "0"
    elif args.white_balance_auto == "on":
        white_balance_auto_value = "1"

    set_camera_controls(
        args.device,
        auto_exposure_value,
        args.exposure_time,
        args.gain,
        args.camera_brightness,
        white_balance_auto_value,
        args.white_balance_temperature,
        args.backlight_compensation,
    )

    print("Starting Raspberry USB motion watch.")
    print(f"Device: {args.device}")
    print(
        f"Monitor: {args.monitor_mode}, {args.input_format} "
        f"{args.input_size}@{args.rate} -> {args.monitor_size[0]}x{args.monitor_size[1]}"
    )
    print(f"Capture: {args.capture_kind}, {args.capture_input_format} {args.capture_size}@{args.capture_rate}")
    print("Press Ctrl+C to stop.")

    process: subprocess.Popen[bytes] | None = None
    temp_context: tempfile.TemporaryDirectory[str] | None = None
    temp_dir: Path | None = None

    if args.monitor_mode == "stream":
        process = start_monitor_stream(
            args.device,
            args.input_format,
            args.input_size,
            args.monitor_size,
            args.rate,
            args.brightness,
            args.contrast,
            args.gamma,
            args.saturation,
        )
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="homecamera-monitor-")
        temp_dir = Path(temp_context.name)

    def stop_process(_signum: int, _frame: object) -> None:
        if process is not None:
            stop_monitor_stream(process)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop_process)
    signal.signal(signal.SIGTERM, stop_process)

    background: bytearray | None = None
    motion_frames = 0
    last_capture_at = 0.0
    last_debug_at = 0.0
    best_debug_score = 0.0
    settle_until = time.monotonic() + args.settle_seconds
    armed = False
    quiet_frames = 0

    try:
        if args.force_capture:
            print("Force capture requested.")
            if process is not None:
                stop_monitor_stream(process)
            output_path = capture_media(
                script_dir,
                args.capture_kind,
                args.device,
                args.capture_input_format,
                args.capture_size,
                args.capture_rate,
                args.video_duration,
                args.output_dir,
                args.brightness,
                args.contrast,
                args.gamma,
                args.saturation,
                args.discord,
                args.message,
            )
            print(output_path)
            if args.monitor_mode == "stream":
                process = start_monitor_stream(
                    args.device,
                    args.input_format,
                    args.input_size,
                    args.monitor_size,
                    args.rate,
                    args.brightness,
                    args.contrast,
                    args.gamma,
                    args.saturation,
                )

        while True:
            if args.monitor_mode == "stream":
                assert process is not None
                assert process.stdout is not None
                frame = process.stdout.read(frame_len)
            else:
                assert temp_dir is not None
                frame = capture_snapshot_frame(
                    script_dir,
                    args.device,
                    args.input_format,
                    args.input_size,
                    args.rate,
                    args.monitor_size,
                    args.brightness,
                    args.contrast,
                    args.gamma,
                    args.saturation,
                    temp_dir,
                )
                time.sleep(args.snapshot_interval)

            if not frame:
                print("ffmpeg stream ended.", file=sys.stderr)
                return (process.wait() if process is not None else 1) or 1
            if len(frame) != frame_len:
                print(f"Incomplete frame received: {len(frame)} != {frame_len}", file=sys.stderr)
                return 1

            if background is None:
                background = bytearray(frame)
                if args.dump_monitor_frame:
                    args.dump_monitor_frame.parent.mkdir(parents=True, exist_ok=True)
                    header = f"P5\n{args.monitor_size[0]} {args.monitor_size[1]}\n255\n".encode()
                    args.dump_monitor_frame.write_bytes(header + frame)
                    print(args.dump_monitor_frame)
                    return 0
                continue

            luma_pct = mean_luma_pct(frame, sample_step)
            score, mean_shift = motion_score(
                frame,
                background,
                args.pixel_delta,
                sample_step,
                normalize_luminance=not args.no_luminance_normalize,
            )
            update_background(background, frame, alpha_percent=args.background_alpha)
            best_debug_score = max(best_debug_score, score)

            now = time.monotonic()
            settling_remaining = max(0.0, settle_until - now)

            if args.simple:
                if settling_remaining > 0.0:
                    motion_frames = 0
                    background = bytearray(frame)
                    armed = False
                else:
                    armed = True
                    if score >= args.threshold:
                        motion_frames += 1
                    else:
                        motion_frames = 0

            elif not armed:
                if settling_remaining > 0.0:
                    quiet_frames = 0
                    motion_frames = 0
                    background = bytearray(frame)
                elif args.arm_after_quiet_frames <= 0:
                    armed = True
                    motion_frames = 0
                    background = bytearray(frame)
                    print("Motion detection armed.")
                elif score < args.threshold:
                    quiet_frames += 1
                    motion_frames = 0
                    if quiet_frames >= args.arm_after_quiet_frames:
                        armed = True
                        background = bytearray(frame)
                        print("Motion detection armed.")
                else:
                    quiet_frames = 0
                    motion_frames = 0
                    background = bytearray(frame)

            elif score >= args.threshold:
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
                    f"luma={luma_pct:.1f}% "
                    f"armed={int(armed)} "
                    f"quiet_frames={quiet_frames}/{args.arm_after_quiet_frames} "
                    f"motion_frames={motion_frames}/{args.consecutive} "
                    f"settling_remaining={settling_remaining:.1f}s "
                    f"cooldown_remaining={cooldown_remaining:.1f}s"
                )
                last_debug_at = now
                best_debug_score = 0.0

            can_capture = cooldown_remaining <= 0.0
            if motion_frames >= args.consecutive and can_capture:
                print(f"Motion detected: score={score:.3f}")
                if process is not None:
                    stop_monitor_stream(process)
                time.sleep(0.5)

                output_path = capture_media(
                    script_dir,
                    args.capture_kind,
                    args.device,
                    args.capture_input_format,
                    args.capture_size,
                    args.capture_rate,
                    args.video_duration,
                    args.output_dir,
                    args.brightness,
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
                settle_until = time.monotonic() + args.settle_seconds
                armed = False
                quiet_frames = 0

                if args.monitor_mode == "stream":
                    process = start_monitor_stream(
                        args.device,
                        args.input_format,
                        args.input_size,
                        args.monitor_size,
                        args.rate,
                        args.brightness,
                        args.contrast,
                        args.gamma,
                        args.saturation,
                    )

    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        if process is not None:
            stop_monitor_stream(process)
        if temp_context is not None:
            temp_context.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
