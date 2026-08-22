#!/usr/bin/env python3
"""Future sm_120 A/B oracle for the exact Gemma 4 attention split."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
WHEEL_SHA256 = "6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b"
CANDIDATE_CONFIG = {
    "backend_per_kind": {
        "sliding_window": "TRITON_ATTN",
        "full_attention": "FLEX_ATTENTION",
    },
    # SM120 rejected the implicit FLEX tile at 156672 live resources. These
    # documented minimum power-of-two tiles preserve the same block-mask
    # semantics while reducing the lowering's live state.
    "flex_attn_block_m": 16,
    "flex_attn_block_n": 16,
    "flex_attn_q_block_size": 16,
    "flex_attn_kv_block_size": 16,
}
CONTROL_CONFIG = {"backend": "TRITON_ATTN"}
PROMPTS = [
    "State the result of 19 * 23 as one integer.",
    "Write one sentence explaining why paged KV caches use slot mappings.",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _arm(args: argparse.Namespace) -> int:
    import torch
    import vllm
    from PIL import Image
    from vllm import LLM, SamplingParams

    # The wheel digest, checked by the parent before either arm, is the build
    # identity. Some official wheels expose the normalized package version.
    if vllm.__version__ not in {"0.26.0", "0.26.0+cu129"}:
        raise RuntimeError(f"unexpected vLLM version: {vllm.__version__}")
    if torch.__version__ != "2.11.0+cu130":
        raise RuntimeError(f"unexpected Torch version: {torch.__version__}")
    if torch.cuda.get_device_capability() != (12, 0):
        raise RuntimeError(
            f"unexpected CUDA capability: {torch.cuda.get_device_capability()}"
        )

    attention_config = CONTROL_CONFIG if args.arm == "control" else CANDIDATE_CONFIG
    llm = LLM(
        model=args.model,
        revision=REVISION,
        tokenizer_revision=REVISION,
        quantization="fp8",
        dtype="bfloat16",
        max_model_len=5000,
        max_num_seqs=2,
        max_num_batched_tokens=65536,
        enforce_eager=True,
        attention_config=attention_config,
        seed=0,
    )
    prompts: list[Any] = [
        *PROMPTS,
        {
            "prompt": (
                "<bos><|turn>user\n<|image|>Describe the dominant color."
                "<turn|>\n<|turn>model\n"
            ),
            "multi_modal_data": {
                "image": Image.new("RGB", (64, 64), color=(32, 64, 96))
            },
        },
    ]
    outputs = llm.generate(
        prompts,
        SamplingParams(temperature=0.0, max_tokens=16, seed=0),
        use_tqdm=False,
    )
    result = {
        "arm": args.arm,
        "vllm_version": vllm.__version__,
        "torch_version": torch.__version__,
        "device_capability": list(torch.cuda.get_device_capability()),
        "attention_config": attention_config,
        "sampler": "native_topk_topp_vllm_use_flashinfer_sampler_0",
        "rows": [
            {
                "prompt_token_ids": list(output.prompt_token_ids),
                "output_token_ids": list(output.outputs[0].token_ids),
                "text": output.outputs[0].text,
                "finish_reason": output.outputs[0].finish_reason,
            }
            for output in outputs
        ],
    }
    Path(args.arm_output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


def _run_arm(script: Path, arm: str, model: str, root: Path) -> dict[str, Any]:
    arm_output = root / f"{arm}.json"
    stdout = root / f"{arm}.stdout"
    stderr = root / f"{arm}.stderr"
    env = dict(os.environ)
    env["VLLM_LOGGING_LEVEL"] = "INFO"
    # Keep exact greedy sampling semantics but select vLLM's supported native
    # top-k/top-p implementation instead of FlashInfer on SM120.
    env["VLLM_USE_FLASHINFER_SAMPLER"] = "0"
    command = [
        sys.executable,
        str(script),
        "--arm",
        arm,
        "--arm-output",
        str(arm_output),
        "--model",
        model,
    ]
    with stdout.open("w") as out_handle, stderr.open("w") as err_handle:
        proc = subprocess.run(
            command,
            env=env,
            stdout=out_handle,
            stderr=err_handle,
            timeout=1800,
            check=False,
        )
    return {
        "arm": arm,
        "exit_code": proc.returncode,
        "output": json.loads(arm_output.read_text()) if arm_output.exists() else None,
        "stdout_artifact": stdout.name,
        "stderr_artifact": stderr.name,
        "stderr_text": stderr.read_text(),
    }


def _parent(args: argparse.Namespace) -> int:
    wheel_digest = _sha256(args.wheel)
    if wheel_digest != WHEEL_SHA256:
        raise RuntimeError(f"wheel digest {wheel_digest} != {WHEEL_SHA256}")
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(dir=args.output, prefix="oracle-") as tmp:
        tmp_path = Path(tmp)
        control = _run_arm(Path(__file__).resolve(), "control", args.model, tmp_path)
        candidate = _run_arm(Path(__file__).resolve(), "candidate", args.model, tmp_path)
        control_rows = None if control["output"] is None else control["output"]["rows"]
        candidate_rows = (
            None if candidate["output"] is None else candidate["output"]["rows"]
        )
        candidate_log = candidate.pop("stderr_text")
        control_log = control.pop("stderr_text")
        path_proof = {
            "control_triton": "TRITON_ATTN" in control_log,
            "candidate_triton": "TRITON_ATTN" in candidate_log,
            "candidate_flex": "FLEX_ATTENTION" in candidate_log,
        }
        classification = (
            "oracle_pass"
            if control["exit_code"] == candidate["exit_code"] == 0
            and control_rows == candidate_rows
            and all(path_proof.values())
            else "oracle_failed"
        )
        result = {
            "schema_version": 1,
            "classification": classification,
            "wheel_sha256": wheel_digest,
            "model": args.model,
            "revision": REVISION,
            "path_proof": path_proof,
            "control": control,
            "candidate": candidate,
            "semantic_oracle": (
                "exact prompt and generated token IDs/text for two text requests "
                "plus one deterministic multimodal-prefix request"
            ),
        }
        for source in tmp_path.iterdir():
            source.replace(args.output / source.name)
    terminal = args.output / "SM120_ATTENTION_SPLIT_ORACLE.json"
    terminal.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["classification"] == "oracle_pass" else 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("control", "candidate"))
    parser.add_argument("--arm-output", type=Path)
    parser.add_argument("--model", default="google/gemma-4-31B-it")
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.arm:
        if args.arm_output is None:
            parser.error("--arm-output is required with --arm")
        return _arm(args)
    if args.wheel is None or args.output is None:
        parser.error("--wheel and --output are required")
    return _parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
