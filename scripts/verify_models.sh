#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"

[[ -n "${H3_DATA_ROOT:-}" && -d "${H3_DATA_ROOT}/models" ]] || die "Run make init first."
python3 "${PROJECT_DIR}/docker/download_models.py" --verify --model-root "${H3_DATA_ROOT}/models"
