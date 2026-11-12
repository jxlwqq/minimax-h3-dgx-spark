#!/usr/bin/env python3
"""Download and verify pinned ComfyUI models from ModelScope using the stdlib.

Partial files stay on the model volume. A download replaces the installed file
only after size and SHA-256 checks, so existing valid weights can be reused.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MANIFEST = Path(__file__).with_name("model_manifest.json")
ENDPOINT = "https://modelscope.cn"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_file(path: Path, entry: dict) -> bool:
    return (path.is_file() and path.stat().st_size == entry["size"]
            and sha256(path) == entry["sha256"])


def download_url(manifest: dict, entry: dict) -> str:
    query = urlencode({"Revision": manifest["revision"], "FilePath": entry["path"]})
    return f"{ENDPOINT}/api/v1/models/{manifest['model_id']}/repo?{query}"


def download_file(url: str, destination: Path, entry: dict, token: str = "") -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    for attempt in range(3):
        try:
            if partial.exists() and partial.stat().st_size >= entry["size"]:
                if valid_file(partial, entry):
                    os.replace(partial, destination)
                    return
                partial.unlink()
            offset = partial.stat().st_size if partial.exists() else 0
            headers = {"User-Agent": "minimax-h3-dgx-spark", "Accept-Encoding": "identity"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            if offset:
                headers["Range"] = f"bytes={offset}-"
            with urlopen(Request(url, headers=headers), timeout=60) as response:
                if response.status == 206:
                    content_range = re.fullmatch(
                        r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if (not content_range or int(content_range[1]) != offset
                            or int(content_range[3]) != entry["size"]):
                        raise ValueError("Invalid Content-Range; refusing to append")
                    mode = "ab" if offset else "wb"
                elif response.status == 200:
                    # A server may ignore Range: replace, never append, the full response.
                    mode = "wb"
                    offset = 0
                else:
                    raise ValueError(f"Unexpected HTTP status: {response.status}")
                print(f"[download] {entry['path']} ({offset}/{entry['size']} bytes)", flush=True)
                with partial.open(mode) as output:
                    received = offset
                    while block := response.read(8 * 1024 * 1024):
                        received += len(block)
                        if received > entry["size"]:
                            raise ValueError("Response exceeds expected model size")
                        output.write(block)
            if not valid_file(partial, entry):
                # Keep a short transfer for resume, but discard a full corrupt file.
                if partial.stat().st_size >= entry["size"]:
                    partial.unlink()
                raise ValueError(f"Size or SHA-256 mismatch: {entry['path']}")
            os.replace(partial, destination)
            return
        except (OSError, ValueError, http.client.HTTPException) as exc:
            if attempt == 2:
                raise
            print(f"[retry] {entry['path']}: {exc}", file=sys.stderr)
            time.sleep(2 ** attempt)


def check_source(manifest: dict, entries: list[dict], token: str = "") -> None:
    query = urlencode({"Revision": manifest["revision"], "Recursive": "true"})
    url = f"{ENDPOINT}/api/v1/models/{manifest['model_id']}/repo/files?{query}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        result = json.load(response)
    if result.get("Code") != 200:
        raise ValueError(f"ModelScope file listing failed: {result.get('Message')}")
    remote = {item["Path"]: item for item in result["Data"]["Files"]}
    for entry in entries:
        item = remote.get(entry["path"], {})
        if item.get("Size") != entry["size"] or item.get("Sha256") != entry["sha256"]:
            raise ValueError(f"ModelScope manifest mismatch: {entry['path']}")
        print(f"[source OK] {entry['path']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", nargs="?", default="fl2va", choices=("fl2va", "r2v", "all"))
    parser.add_argument("--model-root", type=Path, default=Path("/opt/ComfyUI/models"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="Offline size and SHA-256 validation")
    mode.add_argument("--check-source", action="store_true", help="Check remote metadata without downloading weights")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    entries = [entry for entry in manifest["files"]
               if args.group == "all" or entry["group"] == args.group]
    token = os.environ.get("MODELSCOPE_API_TOKEN", "")
    if args.check_source:
        check_source(manifest, entries, token)
        return 0

    args.model_root.mkdir(parents=True, exist_ok=True)
    with (args.model_root / ".h3-models.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("Another model download/verification is running")
        if args.verify and args.group == "fl2va":
            entries += [entry for entry in manifest["files"] if entry["group"] == "r2v"
                        and (args.model_root / entry["path"]).exists()]
        failed = False
        for entry in entries:
            destination = args.model_root / entry["path"]
            if valid_file(destination, entry):
                print(f"[OK] {entry['path']} (size + SHA-256)")
            elif args.verify:
                print(f"[FAIL] Missing, truncated or corrupt: {destination}", file=sys.stderr)
                failed = True
            else:
                download_file(download_url(manifest, entry), destination, entry, token)
                print(f"[ready] {entry['path']} (size + SHA-256)")
        return int(failed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
