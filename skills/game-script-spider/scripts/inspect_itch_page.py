#!/usr/bin/env python3
"""Extract itch.io upload metadata from a saved game page HTML file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def inspect_itch_html(path: Path) -> dict:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    title = norm((soup.select_one("h1") or soup.select_one("title") or soup.new_tag("span")).get_text(" "))
    canonical = soup.select_one("meta[property='og:url'], meta[name='twitter:url']")
    source_url = canonical.get("content") if canonical else None

    uploads = []
    for button in soup.select("a.download_btn[data-upload_id]"):
        upload = button.find_parent(class_="upload")
        name = upload.select_one(".upload_name .name") if upload else None
        size = upload.select_one(".file_size") if upload else None
        version = upload.select_one(".version_name") if upload else None
        date = upload.select_one(".version_date abbr") if upload else None
        platforms = []
        if upload:
            for icon in upload.select(".download_platforms [title]"):
                platforms.append(norm(icon.get("title")))
        uploads.append(
            {
                "upload_id": button.get("data-upload_id"),
                "filename": norm(name.get("title") if name and name.get("title") else name.get_text(" ") if name else ""),
                "size_label": norm(size.get_text(" ") if size else ""),
                "version": norm(version.get_text(" ") if version else ""),
                "version_date": norm(date.get("title") if date else ""),
                "platforms": platforms,
            }
        )

    scripts = "\n".join(script.get_text(" ") for script in soup.select("script"))
    download_url_match = re.search(r'"generate_download_url"\s*:\s*"([^"]+)"|generate_download_url["\']?\s*[:=]\s*["\']([^"\']+)', scripts)
    generate_download_url = None
    if download_url_match:
        generate_download_url = (download_url_match.group(1) or download_url_match.group(2)).replace("\\/", "/")

    return {
        "title": title,
        "source_url": source_url,
        "generate_download_url": generate_download_url,
        "uploads": uploads,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = inspect_itch_html(args.html)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
