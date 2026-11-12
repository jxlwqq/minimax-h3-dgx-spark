#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"

exec python3 "${PROJECT_DIR}/docker/download_models.py" all --check-source
