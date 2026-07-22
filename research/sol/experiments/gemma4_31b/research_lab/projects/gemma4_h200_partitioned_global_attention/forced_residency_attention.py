#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import pathlib


PINNED_SOURCE_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"


REPLACEMENTS = (
    (
        """    sm_scale = sm_scale or 1.0 / (Lq**0.5)
    batch_size, head_num = qo_indptr.shape[0] - 1, q_extend.shape[1]
""",
        """    force_global_residency = (
        _is_cuda
        and CUDA_CAPABILITY[0] == 9
        and Lq == 512
        and Lv == 512
        and q_extend.shape[1] == 32
        and k_extend.shape[1] == 4
        and sliding_window_size <= -1
    )
    kernel_maxnreg = 128 if force_global_residency else None

    if force_global_residency and not getattr(
        extend_attention_fwd, "_forced_global_residency_audited", False
    ):
        import json as _json
        import os as _os

        audit_path = _os.environ.get("PARTITIONED_ATTENTION_AUDIT")
        if audit_path:
            with open(audit_path, "a") as audit_handle:
                audit_handle.write(
                    _json.dumps(
                        {
                            "candidate_path": "extend_attention_fwd.global_head512_maxnreg128",
                            "phase": "runtime_invocation",
                            "qk_head_dim": Lq,
                            "v_head_dim": Lv,
                            "q_heads": q_extend.shape[1],
                            "kv_heads": k_extend.shape[1],
                            "query_tile": BLOCK_M,
                            "key_tile": BLOCK_N,
                            "maxnreg": kernel_maxnreg,
                            "causal_limiter": "value_accumulator_register_live_state",
                            "trade": "local_memory_l2_spill_for_two_cta_residency",
                        },
                        sort_keys=True,
                    )
                    + "\\n"
                )
        extend_attention_fwd._forced_global_residency_audited = True

    sm_scale = sm_scale or 1.0 / (Lq**0.5)
    batch_size, head_num = qo_indptr.shape[0] - 1, q_extend.shape[1]
""",
    ),
    (
        """        num_warps=num_warps,
        num_stages=num_stages,
""",
        """        num_warps=num_warps,
        num_stages=num_stages,
        maxnreg=kernel_maxnreg,
""",
    ),
)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def transform_source(raw: bytes) -> bytes:
    actual = sha256_bytes(raw)
    if actual != PINNED_SOURCE_SHA256:
        raise ValueError(f"pinned_extend_attention_source_mismatch:{actual}")
    text = raw.decode()
    for old, new in REPLACEMENTS:
        if text.count(old) < 1:
            raise ValueError(f"forced_residency_patch_target_missing:{old[:48]!r}")
        text = text.replace(old, new, 1)
    return text.encode()


def write_atomic(path: pathlib.Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(raw)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    transformed = transform_source(args.source.read_bytes())
    write_atomic(args.output, transformed)
    print(
        f"source_sha256={PINNED_SOURCE_SHA256} "
        f"candidate_sha256={sha256_bytes(transformed)} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
