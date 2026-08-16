#!/usr/bin/env python3
"""Apply one source-pinned Triton MLA decode tile intervention."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE = Path("/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/ops/triton_decode_attention.py")
EXPECTED_SHA256 = "cf4debbbbdf2245355177dd7be91c4ac75730a9207a10cd7dab6306a5c3bdec4"
MLA_BACKEND_SOURCE = Path("/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/backends/mla/triton_mla.py")
MLA_BACKEND_EXPECTED_SHA256 = "647a6d5f4c46f3057fdedce04cc2ee3b15ade713b1d7752df00e347efbd62ef6"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--block-n", type=int, choices=(32, 64), required=True)
    parser.add_argument("--num-stages", type=int, choices=(1, 2), required=True)
    parser.add_argument("--num-kv-splits", type=int, choices=(4, 8, 16), required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    before = SOURCE.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    if before_hash != EXPECTED_SHA256:
        raise RuntimeError(f"unexpected vLLM decode source {before_hash}")
    text = before.decode()
    needle = "def _decode_grouped_att_m_fwd(\n"
    start = text.index(needle)
    end = text.index("\n\n@triton.jit", start)
    function = text[start:end]
    old = "    BLOCK = 32\n"
    if function.count(old) != 1:
        raise RuntimeError("expected exactly one grouped decode BLOCK assignment")
    changed = function.replace(old, f"    BLOCK = {args.block_n}\n")
    old_stages = "    num_stages = 2\n"
    if changed.count(old_stages) != 1:
        raise RuntimeError("expected exactly one grouped decode stage assignment")
    changed = changed.replace(old_stages, f"    num_stages = {args.num_stages}\n")
    output = (text[:start] + changed + text[end:]).encode()
    backend_before = MLA_BACKEND_SOURCE.read_bytes()
    backend_before_hash = hashlib.sha256(backend_before).hexdigest()
    if backend_before_hash != MLA_BACKEND_EXPECTED_SHA256:
        raise RuntimeError(f"unexpected vLLM MLA backend source {backend_before_hash}")
    backend_text = backend_before.decode()
    split_needle = "num_kv_splits = 1 if vllm_is_batch_invariant() else 4"
    if backend_text.count(split_needle) != 1:
        raise RuntimeError("expected exactly one non-batch-invariant KV split assignment")
    backend_output = backend_text.replace(
        split_needle,
        f"num_kv_splits = 1 if vllm_is_batch_invariant() else {args.num_kv_splits}",
    ).encode()
    SOURCE.write_bytes(output)
    MLA_BACKEND_SOURCE.write_bytes(backend_output)
    record = {
        "source": str(SOURCE),
        "source_sha256_before": before_hash,
        "source_sha256_after": hashlib.sha256(output).hexdigest(),
        "decode_grouped_block_n_before": 32,
        "decode_grouped_block_n_after": args.block_n,
        "decode_grouped_num_stages_before": 2,
        "decode_grouped_num_stages_after": args.num_stages,
        "changed_occurrences": 1,
        "mla_backend_source": str(MLA_BACKEND_SOURCE),
        "mla_backend_source_sha256_before": backend_before_hash,
        "mla_backend_source_sha256_after": hashlib.sha256(backend_output).hexdigest(),
        "num_kv_splits_before": 4,
        "num_kv_splits_after": args.num_kv_splits,
        "mla_backend_changed_occurrences": 1,
    }
    args.evidence.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
