#!/usr/bin/env python3
"""Submit a video, wait for its outputs, mux audio, and validate the result."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import uuid

TEMPLATE = Path(__file__).resolve().parents[1] / "workflows/minimax_h3_t2v_api.json"


def build_workflow(prompt: str, prefix: str, width: int, height: int,
                   frames: int, seed: int, first_frame: str | None = None) -> dict:
    workflow = copy.deepcopy(json.loads(TEMPLATE.read_text()))
    workflow["7"]["inputs"].update(prompt=prompt, width=width, height=height, length=frames)
    workflow["9"]["inputs"]["seed"] = seed
    workflow["13"]["inputs"]["filename_prefix"] = prefix
    workflow["14"]["inputs"]["filename_prefix"] = "audio/" + prefix
    if first_frame:
        workflow["15"] = {"class_type": "LoadImage", "inputs": {"image": first_frame}}
        workflow["7"]["inputs"]["first_frame"] = ["15", 0]
    return workflow


def api(url: str, payload: dict | None = None) -> dict:
    request = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def wait_for_prompt(base_url: str, prompt_id: str, timeout: float, interval: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = api(f"{base_url}/history/{prompt_id}").get(prompt_id)
        if record:
            status = record.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"Generation failed: {json.dumps(status, ensure_ascii=False)}")
            if status.get("completed"):
                return record["outputs"]
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    raise TimeoutError(f"Timed out waiting for {prompt_id}; inspect /history/{prompt_id} and /queue")


def output_path(outputs: dict, node: str, extensions: tuple[str, ...]) -> str:
    for values in outputs.get(node, {}).values():
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict) or item.get("type") != "output":
                continue
            filename = PurePosixPath(item.get("filename", ""))
            subfolder = PurePosixPath(item.get("subfolder", ""))
            path = subfolder / filename
            if filename.is_absolute() or subfolder.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe output path in ComfyUI history")
            if path.suffix.lower() in extensions:
                return str(PurePosixPath("/opt/ComfyUI/output") / path)
    raise RuntimeError(f"No saved {extensions} output found for node {node}")


def mux_and_validate(container: str, video: str, audio: str, prefix: str) -> str:
    final = f"/opt/ComfyUI/output/{prefix}_final.mp4"
    subprocess.run([
        "docker", "exec", container, "ffmpeg", "-y", "-i", video, "-i", audio,
        "-map", "0:v:0", "-map", "1:a:0", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "copy", "-c:a", "aac", "-shortest", final,
    ], check=True)
    result = subprocess.run([
        "docker", "exec", container, "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type:format=duration", "-of", "json", final,
    ], check=True, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    types = {stream["codec_type"] for stream in metadata.get("streams", [])}
    if not {"video", "audio"} <= types or float(metadata.get("format", {}).get("duration", 0)) <= 0:
        raise RuntimeError(f"Output must have video, audio, and positive duration: {metadata}")
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--container", default="minimax-h3-comfyui")
    parser.add_argument("--prompt", default="A majestic whale swimming in the deep blue ocean, sunlight rays piercing the water surface, cinematic, stereo sound of ocean waves")
    parser.add_argument("--prefix", default="h3_smoke_" + uuid.uuid4().hex[:12])
    parser.add_argument("--width", type=int, default=608)
    parser.add_argument("--height", type=int, default=352)
    parser.add_argument("--frames", type=int, default=96)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--first-frame", help="Reference image filename relative to ComfyUI input/")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--poll-interval", type=float, default=3)
    parser.add_argument("--print-workflow", action="store_true", help="Print API JSON without submitting a task")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.prefix):
        parser.error("--prefix accepts only letters, numbers, underscores and hyphens")
    if args.width <= 0 or args.height <= 0 or not 1 <= args.frames <= 362:
        parser.error("Dimensions must be positive; frames must be between 1 and 362")
    if args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("Timeout and poll interval must be positive")
    workflow = build_workflow(args.prompt, args.prefix, args.width, args.height,
                              args.frames, args.seed, args.first_frame)
    if args.print_workflow:
        print(json.dumps(workflow, indent=2, ensure_ascii=False))
        return 0
    base_url = args.url.rstrip("/")
    response = api(f"{base_url}/prompt", {"prompt": workflow, "client_id": uuid.uuid4().hex})
    if response.get("error") or response.get("node_errors") or "prompt_id" not in response:
        raise RuntimeError(f"Workflow rejected: {json.dumps(response, ensure_ascii=False)}")
    prompt_id = response["prompt_id"]
    print(f"Submitted: {prompt_id}", flush=True)
    outputs = wait_for_prompt(base_url, prompt_id, args.timeout, args.poll_interval)
    video = output_path(outputs, "13", (".mp4", ".webm", ".mkv", ".mov"))
    audio = output_path(outputs, "14", (".flac", ".wav", ".mp3", ".ogg"))
    final = mux_and_validate(args.container, video, audio, args.prefix)
    print(f"Validated video + audio: {final}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
