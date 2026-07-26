#!/usr/bin/env python3
import hashlib
import json
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence" / "upstream"
SOURCES = {
    "vllm/model_executor/models/gemma4.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/model_executor/models/gemma4.py",
        "f101ae257cfe4c71e90ced922da04228468dbb84c01af00a0b48fa681f873a0f",
    ),
    "vllm/model_executor/layers/quantization/fp8.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/model_executor/layers/quantization/fp8.py",
        "26ede801aceeadea1e263b854424ed4fbd0bf5c081bf5beceaf4b877fb1d4fc0",
    ),
    "vllm/model_executor/kernels/linear/scaled_mm/cutlass.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/model_executor/kernels/linear/scaled_mm/cutlass.py",
        "d01b6fe09e3c3fa3991045f6ac7b469a58a550c56426ffd8900badbbe7e5355b",
    ),
    "vllm/csrc/scaled_mm_sm100_fp8_dispatch.cuh": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/scaled_mm_sm100_fp8_dispatch.cuh",
        "96fc8b1bdfca58a6c3999711390385f94f2866b275573511ae7302e79122a355",
    ),
    "vllm/platforms/cuda.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/platforms/cuda.py",
        "ea6cade0bc560dcafea09bef8d30249b949e322ed8696ff02c6d20fa250640d2",
    ),
    "vllm/v1/attention/backends/flashinfer.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/v1/attention/backends/flashinfer.py",
        "e2448a6e8030cd658773e6b6abe9188981db9af0c9c70b8f28284bdc2a093b73",
    ),
    "vllm/utils/flashinfer.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/utils/flashinfer.py",
        "310b4670faf6c81cda01edd4bd30055e000d6cc2f2ce8b54a2ad2711d15317b7",
    ),
    "vllm/v1/attention/backends/flash_attn.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/v1/attention/backends/flash_attn.py",
        "7bcce2c20d361719fea3982c3b90bd13b466d6b4e3383192211e6741ec8147f2",
    ),
    "vllm/v1/attention/backends/triton_attn.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/v1/attention/backends/triton_attn.py",
        "20b4dd5f8c15cd2d6f9598268368f5fc572f2c980eb75327c5992100c49ff3ed",
    ),
    "vllm/v1/attention/ops/triton_decode_attention.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/v1/attention/ops/triton_decode_attention.py",
        "b9823c65eba22d76abf64dad7d7d16a950f67471c86d6cb5b3e983aaf14381ac",
    ),
    "vllm/v1/attention/ops/triton_prefill_attention.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/v1/attention/ops/triton_prefill_attention.py",
        "799473a00984233ff1b659fffa4d67e02d985cd83a413281eba36ef7b8737e27",
    ),
    "vllm/v1/attention/ops/triton_reshape_and_cache_flash.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/v1/attention/ops/triton_reshape_and_cache_flash.py",
        "6cac51475b8c656992a21b2d150acd3a16a95a7ab7d49aab151a3ef13c24b80d",
    ),
    "vllm/model_executor/layers/layernorm.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/model_executor/layers/layernorm.py",
        "3460eba01758849027bb59b8592626406e33ab25b23d2def729bb0ec42afce67",
    ),
    "vllm/model_executor/layers/vocab_parallel_embedding.py": (
        "vllm-project/vllm",
        "8d28b48d01b2ba56e962c7c57b894c6b4fcf8a35",
        "vllm/model_executor/layers/vocab_parallel_embedding.py",
        "60b116e260d5438513c9bb60370306eed5e9b0ce612bfbe0a3885e64fdf0587b",
    ),
    "sglang/python/sglang/srt/models/gemma4_causal.py": (
        "sgl-project/sglang",
        "61057bda6c4b8cda1117d74f100d0735645c0cfb",
        "python/sglang/srt/models/gemma4_causal.py",
        "9c5f5f5739cbec30284302f266fec1d797a86fb98fa1273a27c97fb5d869d001",
    ),
    "sglang/python/sglang/srt/layers/quantization/fp8.py": (
        "sgl-project/sglang",
        "61057bda6c4b8cda1117d74f100d0735645c0cfb",
        "python/sglang/srt/layers/quantization/fp8.py",
        "194e5c5890c6785facb66bc66d2d0f32f141afbe4adbdaa8c641e997a57a786f",
    ),
    "sglang/python/sglang/srt/layers/quantization/fp8_utils.py": (
        "sgl-project/sglang",
        "61057bda6c4b8cda1117d74f100d0735645c0cfb",
        "python/sglang/srt/layers/quantization/fp8_utils.py",
        "fb9115eb582dcb422633424805b3eecff5d415437d8e1c13f0fc2a6cb28573a2",
    ),
    "sglang/python/sglang/srt/layers/attention/triton_backend.py": (
        "sgl-project/sglang",
        "61057bda6c4b8cda1117d74f100d0735645c0cfb",
        "python/sglang/srt/layers/attention/triton_backend.py",
        "ea609d53c9825687bec4dc2c48d200f0209af88350b3d53b61e8ebdf22cdf71a",
    ),
    "sglang/python/sglang/kernels/ops/attention/decode_attention.py": (
        "sgl-project/sglang",
        "61057bda6c4b8cda1117d74f100d0735645c0cfb",
        "python/sglang/kernels/ops/attention/decode_attention.py",
        "7833f6d06115dfd54b384d9ce907a012fa2f568083d90fc0f259e9ef24bf5311",
    ),
    "sglang/python/sglang/kernels/ops/attention/extend_attention.py": (
        "sgl-project/sglang",
        "61057bda6c4b8cda1117d74f100d0735645c0cfb",
        "python/sglang/kernels/ops/attention/extend_attention.py",
        "8c62dc969a6219baf4d43de41bb3ddd47f63f325a186d341b5c549249eb8555b",
    ),
    "sglang/python/sglang/kernels/ops/layernorm/gemma4_fused_ops.py": (
        "sgl-project/sglang",
        "61057bda6c4b8cda1117d74f100d0735645c0cfb",
        "python/sglang/kernels/ops/layernorm/gemma4_fused_ops.py",
        "f9d8c7c3ea71afc1341c2de02807b8fda94e418248bd9ee404b15b3337463ad3",
    ),
    "sglang/sgl-kernel/csrc/gemm/fp8_gemm_kernel.cu": (
        "sgl-project/sglang",
        "61057bda6c4b8cda1117d74f100d0735645c0cfb",
        "sgl-kernel/csrc/gemm/fp8_gemm_kernel.cu",
        "be6f95bb0ef108ebf08b8b84336b6840726beb7fa5bbb90aa6eb4038ce778767",
    ),
    "tensorrt_llm/tensorrt_llm/_torch/configs/gemma4_unified.py": (
        "NVIDIA/TensorRT-LLM",
        "cf44a1ccee7dd3381a7b4c49a8318c0c3ae4426b",
        "tensorrt_llm/_torch/configs/gemma4_unified.py",
        "00e526739a7629b72f3313d7f03c9b9e64a30c9d6dd37e5fd203b7034a925589",
    ),
    "tensorrt_llm/tensorrt_llm/_torch/models/checkpoints/hf/gemma4_weight_mapper.py": (
        "NVIDIA/TensorRT-LLM",
        "cf44a1ccee7dd3381a7b4c49a8318c0c3ae4426b",
        "tensorrt_llm/_torch/models/checkpoints/hf/gemma4_weight_mapper.py",
        "0af10784258c4f2da67f7be0391dc292467f5d31d8ec8bbbd6cd599a0aabfa9a",
    ),
    "tensorrt_llm/tensorrt_llm/_torch/modules/gemma4/fused_qkv.py": (
        "NVIDIA/TensorRT-LLM",
        "cf44a1ccee7dd3381a7b4c49a8318c0c3ae4426b",
        "tensorrt_llm/_torch/modules/gemma4/fused_qkv.py",
        "942931a4d21c7ea68c1acd086d007999c85dde14535ce3d4b639dfe381158cc7",
    ),
    "tensorrt_llm/cpp/fp8_rowwise_gemm_kernel_template_sm100.h": (
        "NVIDIA/TensorRT-LLM",
        "cf44a1ccee7dd3381a7b4c49a8318c0c3ae4426b",
        "cpp/tensorrt_llm/kernels/cutlass_kernels/fp8_rowwise_gemm/fp8_rowwise_gemm_kernel_template_sm100.h",
        "d9dad289999c1e95d43875f1eed1dfa0c675b0d9faefd6a7dfe1b7bd8fdc9a19",
    ),
    "cutlass/test/unit/gemm/device/sm100_tensorop_gemm/f8_f8_void_f32.cu": (
        "NVIDIA/cutlass",
        "e64a9136dd929639e5f7c969fe5af3bf7415cd4f",
        "test/unit/gemm/device/sm100_tensorop_gemm/f8_f8_void_f32.cu",
        "9469015ec08581a1df791582abd81643f10c6ad61018753c6b6975b8e716645d",
    ),
    "flashinfer/csrc/fmha_cutlass_sm100.cu": (
        "flashinfer-ai/flashinfer",
        "290c091865dd07a3a6edcd87e2cde1982632cdfc",
        "csrc/fmha_cutlass_sm100.cu",
        "9d5f5cf52db6f7045a80138985f6e75ef2af5229f9080cd327b5729e2d5e0f01",
    ),
    "flashinfer/flashinfer/decode.py": (
        "flashinfer-ai/flashinfer",
        "290c091865dd07a3a6edcd87e2cde1982632cdfc",
        "flashinfer/decode.py",
        "f6fd0546d22b9de51d1dfc882da581154dde0a2f8e178696083c18e97d6bd4f9",
    ),
    "flashinfer/flashinfer/prefill.py": (
        "flashinfer-ai/flashinfer",
        "290c091865dd07a3a6edcd87e2cde1982632cdfc",
        "flashinfer/prefill.py",
        "7b83362805dabf5d6da80738ab8910be4d0ce60b5dadcbbec2ebdc64594f6525",
    ),
    "flashinfer/tests/attention/test_trtllm_gen_attention_decode.py": (
        "flashinfer-ai/flashinfer",
        "290c091865dd07a3a6edcd87e2cde1982632cdfc",
        "tests/attention/test_trtllm_gen_attention_decode.py",
        "7db575396896d1e287631b80c42b12f08a18cdcd65d93aa9c1af1afb392fce27",
    ),
    "flashinfer/tests/attention/test_trtllm_gen_attention_prefill.py": (
        "flashinfer-ai/flashinfer",
        "290c091865dd07a3a6edcd87e2cde1982632cdfc",
        "tests/attention/test_trtllm_gen_attention_prefill.py",
        "4d26dd681fce04ce124a4cd77b2a9f6f13774810395a14017d2fff67febeb60d",
    ),
    "transformers/src/transformers/models/gemma4/configuration_gemma4.py": (
        "huggingface/transformers",
        "b6d5084fb4a5dd11e44005a5fa009e7943271090",
        "src/transformers/models/gemma4/configuration_gemma4.py",
        "6c84e46db9b22617f42397ce46f1799e82dcd27172a7882a3044d9f83fd4990f",
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    manifest = {}
    for local_name, (repository, revision, upstream_path, expected) in SOURCES.items():
        target = EVIDENCE / local_name
        data = target.read_bytes() if target.is_file() else b""
        if digest(data) != expected:
            url = (
                f"https://raw.githubusercontent.com/{repository}/{revision}/"
                f"{upstream_path}"
            )
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
            actual = digest(data)
            if actual != expected:
                raise RuntimeError(
                    f"source_hash_mismatch:{local_name}:{expected}:{actual}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_suffix(target.suffix + ".part")
            part.write_bytes(data)
            part.replace(target)
        manifest[local_name] = {
            "bytes": len(data),
            "repository": f"https://github.com/{repository}",
            "revision": revision,
            "sha256": expected,
            "upstream_path": upstream_path,
        }
    encoded = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    target = EVIDENCE / "SOURCE_MANIFEST.json"
    part = target.with_suffix(".json.part")
    part.write_text(encoded)
    part.replace(target)


if __name__ == "__main__":
    main()
