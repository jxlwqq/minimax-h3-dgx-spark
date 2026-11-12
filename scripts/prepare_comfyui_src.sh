#!/usr/bin/env bash
# Prepare exactly the ComfyUI ref used by Compose; never overwrite an existing checkout.
set -Eeuo pipefail

requested_ref="${COMFYUI_REF:-}"
source "$(dirname "$0")/common.sh"
REF="${requested_ref:-${COMFYUI_REF:-v0.45.0}}"
SRC="${PROJECT_DIR}/comfyui-src"

if [[ -e "$SRC" ]]; then
  if [[ -d "$SRC/comfy" && -f "$SRC/.h3-source-ref" && "$(cat "$SRC/.h3-source-ref")" == "$REF" ]]; then
    info "ComfyUI ${REF} source already prepared."
    exit 0
  fi
  die "comfyui-src/ is incomplete, untracked or uses another ref. Move it aside, then rerun for ${REF}."
fi

work="$(mktemp -d "${PROJECT_DIR}/.comfyui-src.XXXXXX")"
trap 'rm -rf "$work"' EXIT
info "Downloading ComfyUI ${REF} from codeload..."
curl -fL --retry 3 -o "$work/source.tar.gz" \
  "https://codeload.github.com/Comfy-Org/ComfyUI/tar.gz/refs/tags/${REF}"
mkdir "$work/source"
tar xzf "$work/source.tar.gz" -C "$work/source" --strip-components=1
[[ -d "$work/source/comfy" && -f "$work/source/main.py" ]] || die "Invalid ComfyUI archive."
printf '%s\n' "$REF" > "$work/source/.h3-source-ref"
mv "$work/source" "$SRC"
info "Prepared: ${SRC} (${REF})"
