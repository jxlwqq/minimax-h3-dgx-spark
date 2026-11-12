ARG BASE_IMAGE=nvcr.io/nvidia/pytorch:26.10-py3
ARG DEPENDENCY_BASE_IMAGE=${BASE_IMAGE}

FROM ${DEPENDENCY_BASE_IMAGE} AS dependencies
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_CONSTRAINT="" \
    VIRTUAL_ENV=/opt/h3-venv \
    PATH="/opt/h3-venv/bin:${PATH}"
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=""
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}

# A clean environment uses upstream stable wheels, isolated from NGC's a0 torch
# and extensions compiled against that custom build. The host is not modified.
COPY docker/requirements-stable.txt /tmp/h3-requirements.txt
COPY docker/requirements-lock.txt /tmp/h3-requirements-lock.txt
COPY docker/repair_cusparselt_metadata.py /tmp/h3-repair-cusparselt.py
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv /opt/h3-venv \
    && env -u PIP_NO_CACHE_DIR -u PIP_EXTRA_INDEX_URL python -m pip install \
      --index-url https://pypi.org/simple --upgrade pip setuptools wheel \
    && (env -u PIP_NO_CACHE_DIR python -m pip install --no-deps --require-hashes -r /tmp/h3-requirements-lock.txt \
      || env -u PIP_NO_CACHE_DIR -u PIP_EXTRA_INDEX_URL python -m pip install \
        --index-url https://pypi.org/simple --no-deps --require-hashes -r /tmp/h3-requirements-lock.txt) \
    && python /tmp/h3-repair-cusparselt.py \
    && python -m pip check \
    && python -m pip freeze > /opt/h3-runtime-packages.txt

FROM ${BASE_IMAGE}
ARG COMFYUI_REF=v0.45.0
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_CONSTRAINT="" \
    VIRTUAL_ENV=/opt/h3-venv \
    PATH="/opt/h3-venv/bin:${PATH}" \
    LD_LIBRARY_PATH="/usr/local/cuda/compat/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"

RUN apt-get update && apt-get install -y --no-install-recommends \
      git git-lfs curl ca-certificates ffmpeg \
      libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
      tini procps jq \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install --system

COPY --from=dependencies /opt/h3-venv /opt/h3-venv
COPY --from=dependencies /opt/h3-runtime-packages.txt /opt/h3-runtime-packages.txt
COPY --from=dependencies /opt/h3-runtime-adjustments.json /opt/h3-runtime-adjustments.json
# Prepare the exact release on the host before building.
COPY comfyui-src/ /opt/ComfyUI/
WORKDIR /opt/ComfyUI
RUN test "$(cat .h3-source-ref)" = "${COMFYUI_REF}" \
    && python -c "import torch, comfy.audio; print('torch:', torch.__version__, 'CUDA:', torch.version.cuda)"

# ComfyUI v0.45.0 uses comfy.audio; torchaudio is no longer required.
COPY docker/entrypoint.sh /usr/local/bin/h3-entrypoint
COPY docker/download_models.py /usr/local/bin/h3-download-models
COPY docker/model_manifest.json /usr/local/bin/model_manifest.json
COPY scripts/validate_runtime.py /usr/local/bin/h3-validate-runtime
RUN chmod +x /usr/local/bin/h3-entrypoint /usr/local/bin/h3-download-models

EXPOSE 8188
ENTRYPOINT ["/opt/nvidia/nvidia_entrypoint.sh", "/usr/bin/tini", "--", "/usr/local/bin/h3-entrypoint"]
