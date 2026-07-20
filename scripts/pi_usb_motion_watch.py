#!/usr/bin/env python3
"""Watch a Raspberry Pi USB/V4L2 camera for motion, then capture media."""

from __future__ import annotations

import argparse
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque
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


def block_motion_score(
    frame: bytes,
    background: bytearray,
    frame_size: tuple[int, int],
    block_grid: tuple[int, int],
    pixel_delta: int,
    block_pixel_ratio: float,
    normalize_luminance: bool,
) -> tuple[float, float, int, int, float]:
    width, height = frame_size
    blocks_x, blocks_y = block_grid
    block_width = max(1, width // blocks_x)
    block_height = max(1, height // blocks_y)
    active_blocks = 0
    total_blocks = 0
    max_block_ratio = 0.0
    mean_shift = 0.0

    if normalize_luminance:
        shift_total = 0
        for index, value in enumerate(frame):
            shift_total += value - background[index]
        mean_shift = shift_total / len(frame) if frame else 0.0

    for block_y in range(blocks_y):
        y_start = block_y * block_height
        y_end = height if block_y == blocks_y - 1 else min(height, y_start + block_height)
        for block_x in range(blocks_x):
            x_start = block_x * block_width
            x_end = width if block_x == blocks_x - 1 else min(width, x_start + block_width)
            changed_pixels = 0
            pixel_count = 0

            for y in range(y_start, y_end):
                row_start = y * width
                for x in range(x_start, x_end):
                    index = row_start + x
                    delta = (frame[index] - background[index]) - mean_shift
                    if abs(delta) >= pixel_delta:
                        changed_pixels += 1
                    pixel_count += 1

            block_ratio = changed_pixels / pixel_count if pixel_count else 0.0
            max_block_ratio = max(max_block_ratio, block_ratio)
            if block_ratio >= block_pixel_ratio:
                active_blocks += 1
            total_blocks += 1

    return (
        active_blocks / total_blocks if total_blocks else 0.0,
        mean_shift,
        active_blocks,
        total_blocks,
        max_block_ratio,
    )


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


def rgb_to_gray(frame: bytes) -> bytes:
    gray = bytearray(len(frame) // 3)
    output_index = 0
    for index in range(0, len(frame), 3):
        red = frame[index]
        green = frame[index + 1]
        blue = frame[index + 2]
        gray[output_index] = (77 * red + 150 * green + 29 * blue) // 256
        output_index += 1
    return bytes(gray)


def spot_stats_text(
    rgb_frame: bytes,
    frame_size: tuple[int, int],
    spot_size: tuple[int, int],
    stddev_history: deque[float],
) -> str:
    width, height = frame_size
    spot_width = min(spot_size[0], width)
    spot_height = min(spot_size[1], height)
    x_start = max(0, (width - spot_width) // 2)
    y_start = max(0, (height - spot_height) // 2)
    x_end = x_start + spot_width
    y_end = y_start + spot_height

    red_total = 0
    green_total = 0
    blue_total = 0
    gray_total = 0
    gray_square_total = 0
    count = 0

    for y in range(y_start, y_end):
        row_start = y * width * 3
        for x in range(x_start, x_end):
            index = row_start + (x * 3)
            red = rgb_frame[index]
            green = rgb_frame[index + 1]
            blue = rgb_frame[index + 2]
            gray = (77 * red + 150 * green + 29 * blue) // 256
            red_total += red
            green_total += green
            blue_total += blue
            gray_total += gray
            gray_square_total += gray * gray
            count += 1

    if not count:
        return "spot=empty"

    gray_mean = gray_total / count
    variance = max(0.0, (gray_square_total / count) - (gray_mean * gray_mean))
    gray_stddev = math.sqrt(variance)
    stddev_history.append(gray_stddev)
    gray_stddev_5 = sum(stddev_history) / len(stddev_history)

    return (
        f"spot=center:{spot_width}x{spot_height} "
        f"spot_gray={gray_mean:.1f} "
        f"spot_rgb=({red_total / count:.1f},{green_total / count:.1f},{blue_total / count:.1f}) "
        f"spot_gray_std={gray_stddev:.2f} "
        f"spot_gray_std5={gray_stddev_5:.2f}"
    )


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
    raw_format: str,
) -> subprocess.Popen[bytes]:
    width, height = monitor_size
    video_filter = (
        f"fps={rate},"
        f"eq=brightness={brightness}:contrast={contrast}:gamma={gamma}:saturation={saturation},"
        f"scale={width}:{height},format={raw_format}"
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-probesize",
        "32",
        "-analyzeduration",
        "0",
        "-thread_queue_size",
        "1",
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

    return subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=0)


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
    parser.add_argument(
        "--score-mode",
        choices=("pixel", "block"),
        default="block",
        help="Motion scoring algorithm. block is more robust for noisy MJPEG streams.",
    )
    parser.add_argument(
        "--block-grid",
        default="16x12",
        type=parse_size,
        help="Grid used by --score-mode block. Default: 16x12.",
    )
    parser.add_argument(
        "--block-delta",
        default=None,
        type=float,
        help="Deprecated. Use --pixel-delta and --block-pixel-ratio instead.",
    )
    parser.add_argument(
        "--block-pixel-ratio",
        default=0.02,
        type=float,
        help="Changed-pixel ratio needed for one block to count as moving.",
    )
    parser.add_argument(
        "--min-motion-blocks",
        default=2,
        type=int,
        help="Minimum active blocks required in block mode.",
    )
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
    parser.add_argument(
        "--debug-spot",
        action="store_true",
        help="Log RGB/gray statistics for a centered spot in the monitor image.",
    )
    parser.add_argument(
        "--spot-size",
        default="40x40",
        type=parse_size,
        help="Centered spot size used by --debug-spot. Default: 40x40.",
    )
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
    stream_raw_format = "rgb24" if args.debug_spot else "gray"
    stream_frame_len = frame_len * (3 if args.debug_spot else 1)
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
            stream_raw_format,
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
    frames_since_debug = 0
    best_debug_score = 0.0
    settle_until = time.monotonic() + args.settle_seconds
    armed = False
    quiet_frames = 0
    spot_stddev_history: deque[float] = deque(maxlen=5)

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
                    stream_raw_format,
                )

        while True:
            if args.monitor_mode == "stream":
                assert process is not None
                assert process.stdout is not None
                raw_frame = process.stdout.read(stream_frame_len)
                spot_text = ""
                if not raw_frame:
                    frame = b""
                elif len(raw_frame) != stream_frame_len:
                    print(
                        f"Incomplete raw frame received: {len(raw_frame)} != {stream_frame_len}",
                        file=sys.stderr,
                    )
                    return 1
                elif args.debug_spot:
                    frame = rgb_to_gray(raw_frame)
                    spot_text = spot_stats_text(
                        raw_frame,
                        args.monitor_size,
                        args.spot_size,
                        spot_stddev_history,
                    )
                else:
                    frame = raw_frame
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
                spot_text = ""
                time.sleep(args.snapshot_interval)

            if not frame:
                print("ffmpeg stream ended.", file=sys.stderr)
                return (process.wait() if process is not None else 1) or 1
            if len(frame) != frame_len:
                print(f"Incomplete frame received: {len(frame)} != {frame_len}", file=sys.stderr)
                return 1
            frames_since_debug += 1

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
            if args.score_mode == "block":
                score, mean_shift, active_blocks, total_blocks, max_block_ratio = block_motion_score(
                    frame,
                    background,
                    args.monitor_size,
                    args.block_grid,
                    args.pixel_delta,
                    args.block_pixel_ratio,
                    normalize_luminance=not args.no_luminance_normalize,
                )
                score_is_motion = score >= args.threshold and active_blocks >= args.min_motion_blocks
                motion_units_text = (
                    f"active_blocks={active_blocks}/{total_blocks} "
                    f"max_block_ratio={max_block_ratio:.3f} "
                    f"pixel_delta={args.pixel_delta}"
                )
            else:
                score, mean_shift = motion_score(
                    frame,
                    background,
                    args.pixel_delta,
                    sample_step,
                    normalize_luminance=not args.no_luminance_normalize,
                )
                score_is_motion = score >= args.threshold
                motion_units_text = f"pixel_delta={args.pixel_delta}"
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
                    if score_is_motion:
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

            elif score_is_motion:
                motion_frames += 1
            else:
                motion_frames = 0

            cooldown_remaining = max(0.0, args.cooldown - (now - last_capture_at))
            if args.debug and now - last_debug_at >= 1.0:
                debug_elapsed = now - last_debug_at if last_debug_at else 0.0
                processed_fps = frames_since_debug / debug_elapsed if debug_elapsed > 0 else 0.0
                print(
                    "score="
                    f"{score:.4f} best={best_debug_score:.4f} "
                    f"threshold={args.threshold:.4f} "
                    f"processed_fps={processed_fps:.1f} "
                    f"mean_shift={mean_shift:.1f} "
                    f"luma={luma_pct:.1f}% "
                    f"{spot_text} "
                    f"{motion_units_text} "
                    f"armed={int(armed)} "
                    f"quiet_frames={quiet_frames}/{args.arm_after_quiet_frames} "
                    f"motion_frames={motion_frames}/{args.consecutive} "
                    f"settling_remaining={settling_remaining:.1f}s "
                    f"cooldown_remaining={cooldown_remaining:.1f}s"
                )
                last_debug_at = now
                frames_since_debug = 0
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
                        stream_raw_format,
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
