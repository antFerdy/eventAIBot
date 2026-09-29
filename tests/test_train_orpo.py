import torch

import train_orpo


def test_pick_dtype_uses_bfloat16_on_cuda_with_bf16_support():
    assert train_orpo.pick_dtype(cuda_available=True, bf16_supported=True) == torch.bfloat16


def test_pick_dtype_falls_back_to_float16_on_cuda_without_bf16_support():
    assert train_orpo.pick_dtype(cuda_available=True, bf16_supported=False) == torch.float16


def test_pick_dtype_uses_float32_without_cuda():
    assert train_orpo.pick_dtype(cuda_available=False, bf16_supported=False) == torch.float32
