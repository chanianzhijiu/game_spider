#!/usr/bin/env python3
"""List narrative script candidates inside zip archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


SCRIPT_EXTENSIONS = (".rpy", ".rpyc", ".ink", ".ks", ".json")
ENGINE_PREFIX_HINTS = ("/renpy/common/", "\\renpy\\common\\")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_entry(name: str) -> str:
    lower = name.lower()
    if any(hint in lower for hint in ENGINE_PREFIX_HINTS):
        return "engine"
    if lower.endswith(".rpyc"):
        return "compiled-renpy"
    if lower.endswith(".rpy"):
        return "renpy"
    if lower.endswith(".ink"):
        return "ink"
    if lower.endswith(".ks"):
        return "kiri-kiri"
    if lower.endswith(".json"):
        return "json-candidate"
    return "other"


def scan_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        scripts = []
        for info in entries:
            if info.is_dir():
                continue
            lower = info.filename.lower()
            if lower.endswith(SCRIPT_EXTENSIONS):
                scripts.append(
                    {
                        "path": info.filename,
                        "kind": classify_entry(info.filename),
                        "compressed_size": info.compress_size,
                        "file_size": info.file_size,
                    }
                )
    return {
        "archive": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "entry_count": len(entries),
        "script_count": len(scripts),
        "scripts": scripts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = [scan_zip(path) for path in args.archives]
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
