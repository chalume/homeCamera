#!/usr/bin/env python3
"""Send a captured media file to a Discord webhook.

Usage:
  DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." \
    python3 scripts/send_discord_photo.py captures/test.jpg
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError


def build_multipart(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = f"----homeCamera{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode())
        chunks.append(b"\r\n")

    for name, path in files.items():
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{path.name}"\r\n'
            ).encode()
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def send_media(webhook_url: str, media_path: Path, message: str) -> None:
    payload = json.dumps({"content": message})
    body, boundary = build_multipart(
        fields={"payload_json": payload},
        files={"file": media_path},
    )

    req = request.Request(
        webhook_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "User-Agent": "homeCamera/0.1",
        },
    )

    with request.urlopen(req, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError(f"Discord returned HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("media", type=Path)
    parser.add_argument(
        "--message",
        default="Passage detecte dans le garage.",
        help="Message posted with the photo.",
    )
    args = parser.parse_args()

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL is not set.", file=sys.stderr)
        return 2

    if not args.media.is_file():
        print(f"Media file not found: {args.media}", file=sys.stderr)
        return 2

    try:
        send_media(webhook_url, args.media, args.message)
    except HTTPError as exc:
        details = exc.read().decode(errors="replace")
        print(f"Discord HTTP error {exc.code}: {details}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, RuntimeError) as exc:
        print(f"Failed to send Discord photo: {exc}", file=sys.stderr)
        return 1

    print(f"Sent {args.media} to Discord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
