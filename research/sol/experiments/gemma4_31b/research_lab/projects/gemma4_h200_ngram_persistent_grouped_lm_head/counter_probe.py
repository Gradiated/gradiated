#!/usr/bin/env python3
"""One control/candidate launch for profiler counter attribution."""

from __future__ import annotations

import argparse
import pathlib

import torch

from exact_consumer_component import BATCH, DEPTHS, HIDDEN, load_weight
from grouped_lm_head import grouped_lm_head


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight", required=True, type=pathlib.Path)
    args = parser.parse_args()
    torch.manual_seed(8490)
    weight = load_weight(args.weight)
    hidden = torch.randn(
        (BATCH * DEPTHS, HIDDEN), device="cuda", dtype=torch.bfloat16
    )
    request_major = hidden.reshape(BATCH, DEPTHS, HIDDEN)

    def control():
        return torch.stack(
            [
                torch.matmul(request_major[:, depth, :].contiguous(), weight.T)
                for depth in range(DEPTHS)
            ],
            dim=1,
        )

    def candidate():
        return grouped_lm_head(hidden, weight)

    for operation in (control, candidate):
        value = operation()
        del value
    torch.cuda.synchronize()
    torch.cuda.nvtx.range_push("grouped_lm_head.control_12xm32")
    control_value = control()
    torch.cuda.nvtx.range_pop()
    torch.cuda.nvtx.range_push("grouped_lm_head.candidate_depth_interleaved")
    candidate_value = candidate()
    torch.cuda.nvtx.range_pop()
    checksum = (
        control_value[:, :, 0].float().sum()
        + candidate_value[:, 0].float().sum()
    )
    print(float(checksum.item()))


if __name__ == "__main__":
    main()
