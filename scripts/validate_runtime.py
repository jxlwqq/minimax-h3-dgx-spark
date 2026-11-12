#!/usr/bin/env python3
"""Exercise CUDA kernels and ComfyUI audio without loading model weights."""
import json
from pathlib import Path
import sys
import traceback
import torch

source = Path("/opt/ComfyUI")
if not source.is_dir():
    source = Path(__file__).resolve().parents[1] / "comfyui-src"
sys.path.insert(0, str(source))

result = {'torch': torch.__version__, 'torch_file': torch.__file__, 'python_executable': sys.executable, 'cuda': torch.version.cuda, 'tests': {}}

def check(name, callback):
    try:
        callback()
        result['tests'][name] = 'PASS'
    except Exception:
        result['tests'][name] = traceback.format_exc()

result['cuda_available'] = torch.cuda.is_available()
if result['cuda_available']:
    result['gpu'] = torch.cuda.get_device_name(0)
    result['capability'] = torch.cuda.get_device_capability(0)
    result['architectures'] = torch.cuda.get_arch_list()

    def kernels():
        for dtype in (torch.float32, torch.bfloat16):
            x = torch.randn(256, 256, device='cuda', dtype=dtype)
            assert torch.isfinite(x @ x).all().item()
        x = torch.randn(1, 8, 32, 32, device='cuda', dtype=torch.bfloat16)
        w = torch.randn(8, 8, 3, 3, device='cuda', dtype=torch.bfloat16)
        assert torch.isfinite(torch.nn.functional.conv2d(x, w)).all().item()
        torch.cuda.synchronize()
    check('cuda_matmul_conv2d', kernels)

    def attention():
        from torch.nn.attention import SDPBackend, sdpa_kernel
        q = torch.randn(1, 4, 128, 64, device='cuda', dtype=torch.bfloat16)
        actual = torch.nn.functional.scaled_dot_product_attention(q, q, q)
        with sdpa_kernel(SDPBackend.MATH):
            expected = torch.nn.functional.scaled_dot_product_attention(q, q, q)
        assert torch.isfinite(actual).all().item()
        torch.testing.assert_close(actual, expected, rtol=0.03, atol=0.03)
        torch.cuda.synchronize()
    check('sdpa_against_math', attention)


def audio():
    import comfy.audio
    result['audio_backend'] = 'comfy.audio'
    wave = torch.randn(1, 24000, device='cuda')
    resampled = comfy.audio.resample(wave, 24000, 16000)
    assert resampled.shape[-1] == 16000 and torch.isfinite(resampled).all().item()
    mel = comfy.audio.MelSpectrogram(sample_rate=24000, n_fft=1024, hop_length=256, n_mels=80).cuda()(wave)
    assert torch.isfinite(mel).all().item()
    torch.cuda.synchronize()
check('comfy_audio_resample_mel', audio)
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['cuda_available'] and all(v == 'PASS' for v in result['tests'].values()) else 1)
