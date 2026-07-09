#!/usr/bin/env python3
"""Download one freshly generated signed URL to a file.

Use only for public downloads where the site generated the signed URL through
its normal UI/API flow. Signed URLs are short-lived; do not store them as
durable links.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs


def download(url: str, output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_name(output.name + ".part")
    if part.exists():
        part.unlink()

    digest = hashlib.sha256()
    bytes_written = 0
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=120) as response, part.open("wb") as handle:
        status = getattr(response, "status", None)
        content_length = response.headers.get("content-length")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            digest.update(chunk)
            bytes_written += len(chunk)

    part.replace(output)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return {
        "path": str(output),
        "bytes": bytes_written,
        "sha256": digest.hexdigest(),
        "status_code": status,
        "content_length": content_length,
        "signed_url_host": parsed.netloc,
        "signed_url_path": parsed.path,
        "x_amz_date": (query.get("X-Amz-Date") or [None])[0],
        "x_amz_expires": (query.get("X-Amz-Expires") or [None])[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("signed_url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    data = download(args.signed_url, args.output)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.manifest:
        args.manifest.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
