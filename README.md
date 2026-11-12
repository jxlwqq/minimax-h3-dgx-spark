<div align="center">

<img src="assets/icon.svg" alt="MiniMax H3 on DGX Spark" width="120" />

### 单台 DGX Spark / GB10 上容器化跑通 MiniMax H3 有声视频生成

为 DGX Spark / GB10（ARM64，128GB 统一内存）用户提供一套验证过的端到端部署：ComfyUI + MiniMax H3，文生视频 / 图生视频且带声音，宿主机保持干净。

[![快速开始](https://img.shields.io/badge/行动-快速开始-55e5d5?style=flat)](docs/2026-08-04_MiniMaxH3_第一条视频教程.md) [![故障排查](https://img.shields.io/badge/文档-故障排查-50a6ff?style=flat)](docs/故障排查.md) [![多段创作](https://img.shields.io/badge/教程-多段视频创作-9f86ff?style=flat)](docs/2026-08-04_MiniMaxH3_多段视频创作教程.md)

[![GitHub stars](https://img.shields.io/github/stars/Xplore-LAB/minimax-h3-dgx-spark?style=flat&label=stars&color=gold)](https://github.com/Xplore-LAB/minimax-h3-dgx-spark/stargazers)
[![license](https://img.shields.io/badge/license-MIT-1683c4?style=flat)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-v0.45.0-32b643?style=flat)](https://github.com/Comfy-Org/ComfyUI)
[![Docker](https://img.shields.io/badge/Docker-compose-7e35d5?style=flat)](docker-compose.yml)

**简体中文** · [English](README.en.md)

</div>

---

## ⚡ 一分钟看懂 MiniMax H3 on DGX Spark

本仓库是在单台 NVIDIA DGX Spark / GB10（Blackwell SM121，aarch64，121-128GB 统一内存）上跑通 MiniMax H3 的完整方案：模型权重约 42.5 GB，全部负载跑在 Docker 容器（NGC PyTorch 26.10 + ComfyUI v0.45.0）里，模型、输入、输出挂在外部 NVMe。

| 你想完成的事 | 交付成果 |
|---|---|
| 部署 MiniMax H3 到 DGX Spark | 容器化环境 + 4 个必需模型文件（42.5 GB，断点续传下载） |
| 生成第一条带声音的视频 | HTTP API 全流程脚本，约 2-5 分钟出片 |
| 制作多段拼接长视频 | 8 段 × 5 秒拼成 40 秒大片的完整配方 |

## ✨ 核心能力

- **全容器化**：宿主机只装 DGX OS + 驱动 + Docker + NVIDIA Container Toolkit，ComfyUI 与依赖全部在容器内，应用依赖置于容器内独立 Python 环境
- **有声视频**：除视频 VAE（FP16，5.21 GB）外还带 Audio VAE（FP32，0.605 GB），音画联合输出
- **完整模型栈**：FL2VA pruned INT8 convrot 主模型（21.0 GB）+ Qwen3-VL-32B NVFP4 AWQ 文本编码器（15.7 GB）
- **工程化脚本**：`scripts/` 提供 init_storage、preflight、download、verify_models、status、collect_diagnostics 全流程工具
- **排障手册**：13 节故障排查文档 + 基准测试记录表 + 架构与优化说明

## 🚀 快速开始

### 1. 初始化与检查

```bash
make init DATA_ROOT=/mnt/<你的NVMe>/minimax-h3
make preflight
```

### 2. 构建环境

```bash
make build       # 准备 ComfyUI 正式版源码，并构建独立的稳定版 Python 环境
make gpu-check   # 应输出 CUDA 可用、GPU 为 NVIDIA GB10
```

源码从各自 GitHub 上游获取，模型权重统一从 [ModelScope 国内站](https://modelscope.cn/models/Comfy-Org/MiniMax-H3) 下载。`make build` 会校验 ComfyUI 源码版本；如已有旧的 `comfyui-src/` 且版本不匹配或缺少标记，请先移走该目录再构建。

当前升级目标为 NGC `26.10-py3` + ComfyUI `v0.45.0`。NGC 内置的 torch 是 `2.15.0a0` 定制版；本项目在容器内创建 `/opt/h3-venv`，使用上游正式版 PyTorch `2.15.0` 和 torchvision `0.29.2`，与 NGC 的 Python 扩展隔离，宿主机不安装这些依赖。

应用直接依赖固定在 `docker/requirements-stable.txt`，间接依赖固定在 `docker/requirements-lock.txt`（2026-11-11 核对的稳定版）；完整安装结果保存在镜像内 `/opt/h3-runtime-packages.txt`。ComfyUI 配套前端为 `1.58.7`、工作流模板为 `0.11.106`、内嵌文档为 `0.5.16`、comfy-kitchen 为 `0.2.41`、comfy-aimdo 为 `0.6.0`。系统组件由 NGC/Ubuntu 的软件包渠道维护。

PyTorch 2.15.0 固定的 cuSPARSELt 0.8.1 ARM wheel 存在已确认的平台标签错误（`sbsa`）。构建会验证原生库为 AArch64 且与 RECORD 校验值一致后，仅修正 WHEEL 标签及对应 RECORD 项，记录于 `/opt/h3-runtime-adjustments.json`，随后执行完整 `pip check`。详见 [上游问题](https://github.com/pytorch/pytorch/issues/202632)。

ComfyUI v0.45.0 的 H3 节点和音频预处理使用 `comfy.audio`，已移除 torchaudio 依赖；旧的 `87ff22e49ed0` 编译步骤不再需要。历史性能数据仍来自 NGC 25.11 / ComfyUI v0.30.0，不能视为新环境的实测结果。

2026-11-11 已在 GB10 / 驱动 580.178.04 上通过新环境的 CUDA 算子、实际 H3 音频 VAE 和完整文生音视频测试。608×352、请求 96 帧、20 步的冷启动任务耗时 135.87 秒，输出 107 帧 / 4.458 秒；参数和验收范围见 [基准测试记录](docs/基准测试记录表.md#7-2026-11-11-ngc-2610-升级验收)。完整版本核对见 [架构说明](docs/架构与优化说明.md#2026-11-11-版本核对)。

### 3. 下载模型与启动

```bash
make check-model-source  # 核对 ModelScope 的文件清单，不下载权重
make download            # 仅下载 4 个必需文件，支持 .part 断点续传
make verify-models       # 离线检查完整大小和 SHA-256，读取约 42.5 GB 文件
make up
make status
```

模型清单与校验值保存在 `docker/model_manifest.json`。有效的已有模型直接复用；损坏文件在新文件下载并校验成功后才会被替换。下载中间文件与模型在同一数据盘，需为待替换文件预留空间。可选 Ref2VA 使用 `make download-r2v`（额外约 21 GB）。

公开模型通常无需认证；需要认证时在 `.env` 中填写 `MODELSCOPE_API_TOKEN`，不要提交到 Git。旧的 `HF_TOKEN` / `HF_ENDPOINT` 不再控制模型下载，已有 `hf-cache/` 不会自动删除。

⚠️ 生成视频时不要并行跑其他大模型容器（qwen/vllm 等），统一内存会被打满。

### 4. 生成并验收第一条有声视频

```bash
make smoke  # 608×352、96 帧：提交 → 等待 → loudnorm 合成 → ffprobe 验证音视频轨道

# 自定义提示词，或通过 --first-frame image.png 使用 input/ 中的参考图
./scripts/smoke.sh --prompt "A whale in the ocean, clear and audible ocean sounds" --prefix whale

# 仅查看工作流，不提交任务
./scripts/smoke.sh --print-workflow
```

工作流模板在 `workflows/minimax_h3_t2v_api.json`。脚本从任务 history 中读取实际文件名，成片写入 `<H3_DATA_ROOT>/output/<prefix>_final.mp4`。默认等待上限 30 分钟，可用 `--timeout` 调整；超时会返回错误，但不会取消服务中的任务。该检查验证文件轨道与时长，画面质量、可听响度和音画同步仍需人工验收。

H3 将帧数向上对齐至 `17k+5`，因此 `--frames 96` 实际输出 107 帧，24 fps 下约 4.46 秒。容器的临时文件位于挂载目录 `temp/temp/`，使 ComfyUI 可以清理子目录而不删除挂载点。

手动操作与多段拼接见下方教程。

核心节点链：`UNETLoader(FL2VA) + CLIPLoader(Qwen3VL) + VAELoader×2(视频+音频) → MiniMaxH3SigmaShift → MiniMaxH3ImageToVideo → KSampler(20步, cfg=1.0) → VAEDecode + VAEDecodeAudio → CreateVideo/SaveVideo + SaveAudio`

完整可跑脚本见 [第一条视频教程](docs/2026-08-04_MiniMaxH3_第一条视频教程.md)，核心参数：

| 参数 | 值 | 说明 |
|---|---|---|
| `length` | 96≈4s / 124≈5s / 362≈15s | 24fps，上限 15s |
| `width×height` | 608×352 ~ 1216×672 | 0.2MP ~ 0.8MP |
| `steps/cfg` | 20 / 1.0 | H3 官方推荐，euler/simple |
| 音画 | SaveVideo + SaveAudio | 输出后 loudnorm 归一化合成（电平默认 -34dB 听不见） |

图生视频：参考图放 `<NVMe>/minimax-h3/input/`，加 `LoadImage` 节点接到 `MiniMaxH3ImageToVideo.first_frame`。

## 📊 实测性能（GB10, 2026-08-04）

| 任务 | 分辨率 | 时长 | 耗时 |
|---|---:|---:|---:|
| 冒烟 | 608×352 | 4s | 96.8s |
| 常规 | 736×416 | 5s | 179.9s |
| 日常 | 864×480 | 5s | 255.8s（20 步） |
| 图生（竖） | 768×1152 | 5s | 15min 22s |
| 多段拼接 | 8×5s → 40s 大片 | — | ~50min（含合成拼接） |

规律：采样约 26-47s/步，耗时 ≈ 帧数 × 分辨率；竖屏/高分辨率显著变慢。

## 🛡️ 边界与注意

- 依赖变更应写入 Dockerfile 并重新构建，保证容器重建后仍可复现
- 修改依赖应更新版本清单并重新构建；CUDA 不可用时先运行 `make gpu-check`
- 退出码 137 或系统卡顿说明统一内存压力打满，停掉其他大模型容器并降低分辨率
- 视频无声音说明 workflow 缺音频节点，需接 VAEDecodeAudio + SaveAudio
- 服务仅通过 SSH 隧道或可信局域网访问

## 📚 文档导航

- [第一条视频教程](docs/2026-08-04_MiniMaxH3_第一条视频教程.md)：HTTP API 全流程脚本
- [多段视频创作教程](docs/2026-08-04_MiniMaxH3_多段视频创作教程.md)：多段拼接长片配方
- [故障排查](docs/故障排查.md)：13 节完整排障手册
- [基准测试记录表](docs/基准测试记录表.md)：实测耗时记录
- [架构与优化说明](docs/架构与优化说明.md)：方案设计细节
- [提示词模板](docs/提示词模板.md)：视频生成提示词参考

## ✅ 完成标准

- [ ] `make gpu-check` 通过，8188 返回 200
- [ ] `docker exec minimax-h3-comfyui python -c "import torch, comfy.audio; print(torch.__version__)"` 通过
- [ ] `make smoke` 完成，成片包含视频和音频轨道
- [ ] 608×352 / 736×416 / 864×480 三档连续生成成功
- [ ] 输出同时含视频与音频（音画联合）
- [ ] 图生视频（照片→动态）成功
- [ ] 服务仅通过 SSH 隧道或可信局域网访问

## 📄 许可证

- 本仓库代码：[MIT](LICENSE)
- MiniMax H3 模型：Community License（非 Apache 2.0），商用前请核查模型仓库 LICENSE 与所在地区限制
