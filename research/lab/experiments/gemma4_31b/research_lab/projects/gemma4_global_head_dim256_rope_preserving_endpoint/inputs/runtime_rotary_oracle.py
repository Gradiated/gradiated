#!/usr/bin/env python3
import hashlib
import json
import pathlib

import torch

from sglang.srt.layers.rotary_embedding import get_rope
from sglang.srt.server_args import set_global_server_args_for_scheduler


class OracleServerArgs:
    rl_on_policy_target = None


def build(head_dim: int, partial_rotary_factor: float):
    return get_rope(
        head_dim,
        rotary_dim=head_dim,
        max_position=5000,
        base=10000.0,
        rope_scaling={"rope_type": "default"},
        partial_rotary_factor=partial_rotary_factor,
        is_neox_style=True,
    )


def main() -> int:
    set_global_server_args_for_scheduler(OracleServerArgs())
    original = build(512, 0.25)
    candidate = build(256, 0.5)
    original_inv_freq = original._compute_inv_freq(original.base).detach().to(dtype=torch.float64, device="cpu")
    candidate_inv_freq = candidate._compute_inv_freq(candidate.base).detach().to(dtype=torch.float64, device="cpu")
    same_shape = original_inv_freq.shape == candidate_inv_freq.shape
    exact_match = same_shape and torch.equal(original_inv_freq, candidate_inv_freq)
    maximum_delta = (
        float(torch.max(torch.abs(original_inv_freq - candidate_inv_freq)).item())
        if same_shape
        else None
    )
    result = {
        "schema_version": 1,
        "pass": bool(exact_match and original_inv_freq.numel() * 2 == 128),
        "classification": "runtime_inverse_frequency_oracle",
        "original": {"head_dim": 512, "partial_rotary_factor": 0.25},
        "candidate": {"head_dim": 256, "partial_rotary_factor": 0.5},
        "frequency_count": original_inv_freq.numel(),
        "represented_coordinate_count": original_inv_freq.numel() * 2,
        "exact_match": bool(exact_match),
        "max_abs_delta": maximum_delta,
        "tensor_sha256": hashlib.sha256(original_inv_freq.numpy().tobytes()).hexdigest(),
    }
    output = pathlib.Path("/work/rotary-runtime-oracle.json")
    temporary = output.with_suffix(".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
