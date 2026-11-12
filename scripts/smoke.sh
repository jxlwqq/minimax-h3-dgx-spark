#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"

exec python3 "${PROJECT_DIR}/scripts/generate_video.py" \
  --url "http://127.0.0.1:${COMFYUI_PORT:-8188}" "$@"
