#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import torch

from ring_kv import ring_decode_attention, store_ring_kv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    device = "cuda"
    k_ring = torch.zeros(
        (2, 1024, 16, 256), dtype=torch.float8_e5m2, device=device
    )
    v_ring = torch.zeros_like(k_ring)
    valid_k = torch.ones((1, 16, 256), dtype=torch.bfloat16, device=device)
    valid_v = torch.full_like(valid_k, 0.5)
    store_ring_kv(
        valid_k,
        valid_v,
        k_ring,
        v_ring,
        torch.tensor([0], dtype=torch.int32, device=device),
        torch.tensor([0], dtype=torch.int32, device=device),
    )
    before_k = k_ring.view(torch.uint8).clone()
    before_v = v_ring.view(torch.uint8).clone()
    store_ring_kv(
        torch.full_like(valid_k, 57344.0),
        torch.full_like(valid_v, -57344.0),
        k_ring,
        v_ring,
        torch.tensor([-1], dtype=torch.int32, device=device),
        torch.tensor([17], dtype=torch.int32, device=device),
    )

    q = torch.zeros((2, 32, 256), dtype=torch.bfloat16, device=device)
    output = torch.full_like(q, float("nan"))
    kv_indptr = torch.tensor([0, 1, 1], dtype=torch.int32, device=device)
    logits = torch.empty((2, 32, 1, 256), dtype=torch.float32, device=device)
    lse = torch.empty((2, 32, 1), dtype=torch.float32, device=device)
    ring_decode_attention(
        q,
        k_ring,
        v_ring,
        output,
        torch.tensor([1, 0], dtype=torch.int32, device=device),
        torch.tensor([0, 0], dtype=torch.int32, device=device),
        kv_indptr,
        logits,
        lse,
        torch.tensor([1, 1], dtype=torch.int32, device=device),
        1,
        1 / math.sqrt(256),
        1.0,
        1.0,
        request_ids=torch.tensor([0, -1], dtype=torch.int32, device=device),
    )
    torch.cuda.synchronize()
    producer_noop = bool(
        torch.equal(before_k, k_ring.view(torch.uint8))
        and torch.equal(before_v, v_ring.view(torch.uint8))
    )
    consumer_noop = bool(torch.count_nonzero(output[1]).item() == 0)
    valid_finite = bool(torch.isfinite(output[0]).all().item())
    value = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "padded_row_noop_pass"
        if producer_noop and consumer_noop and valid_finite
        else "padded_row_noop_fail",
        "pass": producer_noop and consumer_noop and valid_finite,
        "request_rows": [0, -1],
        "producer_negative_row_noop": producer_noop,
        "consumer_negative_row_zero": consumer_noop,
        "valid_row_finite": valid_finite,
    }
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return 0 if value["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
