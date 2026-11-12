#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"

[[ -f .env ]] || die ".env not found."
[[ -d "${H3_DATA_ROOT:-}" ]] || die "Invalid H3_DATA_ROOT."

info "Downloading MiniMax H3 FL2VA baseline from modelscope.cn..."
info "Approximate model storage: 42.5 GB."
info "Files are written directly to the external model volume."

docker compose run --rm --no-deps \
  --entrypoint python comfyui /usr/local/bin/h3-download-models fl2va

# The downloader validates size + SHA-256 before publishing each file.
