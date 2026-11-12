<div align="center">

<img src="assets/icon.svg" alt="MiniMax H3 on DGX Spark" width="120" />

### Run MiniMax H3 video generation with sound on a single DGX Spark / GB10, fully containerized

A verified end-to-end deployment of ComfyUI + MiniMax H3 (text-to-video / image-to-video, with audio) on NVIDIA DGX Spark / GB10 (ARM64, 128GB unified memory), while keeping the host clean.

[![Quick Start](https://img.shields.io/badge/action-quick%20start-55e5d5?style=flat)](docs/2026-08-04_MiniMaxH3_第一条视频教程.md) [![Troubleshooting](https://img.shields.io/badge/docs-troubleshooting-50a6ff?style=flat)](docs/故障排查.md) [![Multi-segment Guide](https://img.shields.io/badge/guide-multi--segment%20film-9f86ff?style=flat)](docs/2026-08-04_MiniMaxH3_多段视频创作教程.md)

[![GitHub stars](https://img.shields.io/github/stars/Xplore-LAB/minimax-h3-dgx-spark?style=flat&label=stars&color=gold)](https://github.com/Xplore-LAB/minimax-h3-dgx-spark/stargazers)
[![license](https://img.shields.io/badge/license-MIT-1683c4?style=flat)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-v0.45.0-32b643?style=flat)](https://github.com/Comfy-Org/ComfyUI)
[![Docker](https://img.shields.io/badge/Docker-compose-7e35d5?style=flat)](docker-compose.yml)

[简体中文](README.md) · **English**

</div>

---

## ⚡ MiniMax H3 on DGX Spark in One Minute

This repo is a complete recipe for running MiniMax H3 on a single NVIDIA DGX Spark / GB10 (Blackwell SM121, aarch64, 121-128GB unified memory). Weights total about 42.5 GB, everything runs inside Docker (NGC PyTorch 26.10 + ComfyUI v0.45.0), and models, inputs, and outputs live on an external NVMe drive.

| What you want to do | What you get |
|---|---|
| Deploy MiniMax H3 on DGX Spark | Containerized environment + 4 required model files (42.5 GB, resumable download) |
| Generate your first video with sound | Full HTTP API workflow, about 2-5 minutes per clip |
| Produce a multi-segment film | Complete recipe for stitching 8 x 5s segments into a 40s film |

## ✨ Key Capabilities

- **Fully containerized**: the host only needs DGX OS, drivers, Docker, and NVIDIA Container Toolkit; ComfyUI and all dependencies live in the container, and application dependencies use an isolated Python environment
- **Video with sound**: besides the video VAE (FP16, 5.21 GB) there is an audio VAE (FP32, 0.605 GB) for joint audio-video output
- **Full model stack**: FL2VA pruned INT8 convrot main model (21.0 GB) + Qwen3-VL-32B NVFP4 AWQ text encoder (15.7 GB)
- **Engineering scripts**: `scripts/` ships init_storage, preflight, download, verify_models, status, and collect_diagnostics tooling
- **Troubleshooting handbook**: a 13-section troubleshooting doc plus benchmark log and architecture notes

## 🚀 Quick Start

### 1. Initialize and check

```bash
make init DATA_ROOT=/mnt/<your-NVMe>/minimax-h3
make preflight
```

### 2. Build the environment

```bash
make build       # prepares release sources and builds an isolated stable Python environment
make gpu-check   # should report CUDA available and NVIDIA GB10
```

Source code comes from its GitHub upstreams. Model weights come from [ModelScope China](https://modelscope.cn/models/Comfy-Org/MiniMax-H3). Builds validate the ComfyUI source version against `COMFYUI_REF`. Move an old or unmarked `comfyui-src/` aside before rebuilding.

The upgrade target is NGC `26.10-py3` + ComfyUI `v0.45.0`. NGC contains a custom `2.15.0a0` torch build. This project creates `/opt/h3-venv` inside the container and installs upstream stable PyTorch `2.15.0` and torchvision `0.29.2`, isolated from NGC Python extensions. The host does not install these dependencies.

Direct application dependencies are pinned in `docker/requirements-stable.txt`, and transitive dependencies in `docker/requirements-lock.txt` (stable releases checked on 2026-11-11). The installed package list is stored at `/opt/h3-runtime-packages.txt` in the image. The frontend is `1.58.7`, workflow templates `0.11.106`, embedded docs `0.5.16`, comfy-kitchen `0.2.41`, and comfy-aimdo `0.6.0`. System packages follow the NGC/Ubuntu package channels.

PyTorch 2.15.0 pins cuSPARSELt 0.8.1, whose ARM wheel has a confirmed `sbsa` platform-tag defect. The build verifies AArch64 native libraries against RECORD, corrects only the WHEEL tag and its RECORD entry, records the adjustment in `/opt/h3-runtime-adjustments.json`, then runs full `pip check`. See the [upstream issue](https://github.com/pytorch/pytorch/issues/202632).

ComfyUI v0.45.0 uses `comfy.audio` in its H3 nodes and audio preprocessing. It no longer requires torchaudio, so the old `87ff22e49ed0` source-build workaround is removed. Historical performance measurements still refer to NGC 25.11 / ComfyUI v0.30.0 and do not validate the upgraded environment.

On 2026-11-11, the upgraded environment passed CUDA operator tests, actual H3 audio VAE encode/decode, and complete text-to-video generation with audio on GB10 / driver 580.178.04. A cold-start 608×352 job requesting 96 frames with 20 sampling steps completed in 135.87 seconds and produced 107 frames / 4.458 seconds. See the [validation record](docs/基准测试记录表.md#7-2026-11-11-ngc-2610-升级验收) for the exact configuration and coverage.

### 3. Download models and launch

```bash
make check-model-source  # compare ModelScope metadata without downloading weights
make download            # four required files, resumable .part downloads
make verify-models       # offline full-size and SHA-256 checks; reads about 42.5 GB
make up
make status
```

Paths, sizes and SHA-256 checksums are pinned in `docker/model_manifest.json`. Valid existing models are reused. A corrupt installed file is replaced only after a new download passes validation; allow disk space for the replacement. `make download-r2v` adds the optional Ref2VA model (about 21 GB).

Public models normally need no authentication. Set `MODELSCOPE_API_TOKEN` in `.env` if required, and never commit it. `HF_TOKEN` / `HF_ENDPOINT` no longer control these downloads. Existing `hf-cache/` directories are left intact.

⚠️ Do not run other large-model containers alongside video generation; they compete for unified memory.

### 4. Generate and validate a video with sound

```bash
make smoke  # 608×352, 96 frames: submit, wait, normalize/mux, validate audio/video tracks
./scripts/smoke.sh --prompt "A whale in the ocean, clear and audible ocean sounds" --prefix whale
./scripts/smoke.sh --print-workflow  # preview API JSON without submitting
```

The template is `workflows/minimax_h3_t2v_api.json`. Use `--first-frame image.png` for an image in `input/`. The script obtains actual filenames from task history and writes `<H3_DATA_ROOT>/output/<prefix>_final.mp4`. The default timeout is 30 minutes (`--timeout` overrides it); a timeout does not cancel the queued/running task. Track presence and duration are checked automatically; picture quality, audible loudness and synchronization still require human review.

Manual steps and multi-segment stitching are documented below.

Core node chain: `UNETLoader(FL2VA) + CLIPLoader(Qwen3VL) + VAELoader x2 (video + audio) → MiniMaxH3SigmaShift → MiniMaxH3ImageToVideo → KSampler (20 steps, cfg=1.0) → VAEDecode + VAEDecodeAudio → CreateVideo/SaveVideo + SaveAudio`

A full runnable script is in the [first-video tutorial](docs/2026-08-04_MiniMaxH3_第一条视频教程.md). Key parameters:

| Parameter | Value | Notes |
|---|---|---|
| `length` | 96≈4s / 124≈5s / 362≈15s | 24fps, 15s cap |
| `width×height` | 608×352 ~ 1216×672 | 0.2MP ~ 0.8MP |
| `steps/cfg` | 20 / 1.0 | H3 official recommendation, euler/simple |
| A/V | SaveVideo + SaveAudio | loudnorm-normalized after export (default level -34dB is inaudible) |

Image-to-video: place the reference image in `<NVMe>/minimax-h3/input/` and wire a `LoadImage` node into `MiniMaxH3ImageToVideo.first_frame`.

## 📊 Measured Performance (GB10, 2026-08-04)

| Task | Resolution | Duration | Time |
|---|---:|---:|---:|
| Smoke test | 608×352 | 4s | 96.8s |
| Standard | 736×416 | 5s | 179.9s |
| Daily use | 864×480 | 5s | 255.8s (20 steps) |
| I2V (portrait) | 768×1152 | 5s | 15min 22s |
| Multi-segment | 8×5s → 40s film | — | ~50min (incl. compositing) |

Pattern: sampling runs about 26-47s per step; time scales with frames × resolution; portrait/high resolutions are significantly slower.

## 🛡️ Boundaries and Caveats

- Record dependency changes in the Dockerfile and rebuild the image so recreated containers remain reproducible
- Update the dependency pins and rebuild when changing packages; run `make gpu-check` to diagnose CUDA availability
- Exit code 137 or system stalls mean unified memory pressure; stop other large-model containers and lower the resolution
- Silent video means the workflow lacks audio nodes; wire in VAEDecodeAudio + SaveAudio
- Expose the service only through an SSH tunnel or a trusted LAN

## 📚 Documentation

- [First-video tutorial](docs/2026-08-04_MiniMaxH3_第一条视频教程.md): full HTTP API workflow script
- [Multi-segment film tutorial](docs/2026-08-04_MiniMaxH3_多段视频创作教程.md): stitching recipe for longer films
- [Troubleshooting](docs/故障排查.md): the full 13-section handbook
- [Benchmark log](docs/基准测试记录表.md): measured runtimes
- [Architecture and optimization notes](docs/架构与优化说明.md): design details
- [Prompt templates](docs/提示词模板.md): prompt references for video generation

Note: the docs are currently written in Chinese.

## ✅ Definition of Done

- [ ] `make gpu-check` passes, port 8188 returns 200
- [ ] `docker exec minimax-h3-comfyui python -c "import torch, comfy.audio; print(torch.__version__)"` works
- [ ] `make smoke` completes and the result has video and audio tracks
- [ ] Three consecutive generations succeed at 608×352 / 736×416 / 864×480
- [ ] Output contains both video and audio (joint A/V)
- [ ] Image-to-video (photo to motion) works
- [ ] Service is reachable only via SSH tunnel or trusted LAN

## 📄 License

- Code in this repo: [MIT](LICENSE)
- MiniMax H3 model: Community License (not Apache 2.0); check the model repo LICENSE and your local regulations before commercial use
