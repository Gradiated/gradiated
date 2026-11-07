"""Microbenchmarks that calibrate the cost model's measured tier.

Run on the GPU host under the GPU lock: HBM copy bandwidth, and NCCL
all-reduce / all-to-all latency curves across the visible GPUs.
"""

from __future__ import annotations

import json
import os
import sys

import torch
import torch.distributed as dist
import torch.multiprocessing as mp

SIZES = [2**k for k in range(10, 27)]


def _time(fn, iters: int = 100, warmup: int = 30) -> float:
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    if dist.is_initialized():
        dist.barrier()
        torch.cuda.synchronize()
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    for _ in range(iters):
        fn()
    end.record()
    torch.cuda.synchronize()
    return start.elapsed_time(end) / iters / 1e3


def _copy_time(big, dst) -> float:
    for _ in range(3):
        dst.copy_(big)
    torch.cuda.synchronize()
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    for _ in range(20):
        dst.copy_(big)
    end.record()
    torch.cuda.synchronize()
    return start.elapsed_time(end) / 20 / 1e3


def _worker(rank: int, world: int, out_path: str) -> None:
    os.environ.setdefault("MASTER_ADDR", "127.0.0.1")
    os.environ.setdefault("MASTER_PORT", "29571")
    torch.cuda.set_device(rank)
    dist.init_process_group("nccl", rank=rank, world_size=world)
    rows = []
    for size in SIZES:
        tensor = torch.ones(size // 2, dtype=torch.bfloat16, device="cuda")
        seconds = _time(lambda: dist.all_reduce(tensor))
        rows.append({"kind": "all_reduce", "n": world, "bytes": size, "s": seconds})
        send = torch.ones(size // 2, dtype=torch.bfloat16, device="cuda")
        recv = torch.empty_like(send)
        seconds = _time(lambda: dist.all_to_all_single(recv, send))
        rows.append({"kind": "all_to_all", "n": world, "bytes": size, "s": seconds})
    dist.barrier()
    if rank == 0:
        big = torch.empty(4 << 30, dtype=torch.uint8, device="cuda")
        dst = torch.empty_like(big)
        seconds = _copy_time(big, dst)
        rows.append({"kind": "hbm_copy", "bytes": 2 * big.numel(), "s": seconds, "bw": 2 * big.numel() / seconds})
        del big, dst
        with open(out_path, "w") as handle:
            json.dump(rows, handle)
    dist.barrier()
    dist.destroy_process_group()


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "/home/tkcc/run/micro.json"
    world = torch.cuda.device_count()
    mp.spawn(_worker, args=(world, out), nprocs=world, join=True)
    rows = json.load(open(out))
    for row in rows:
        if row["kind"] == "hbm_copy" or row["bytes"] in (1024, 16384, 262144, 4194304, 67108864):
            print(json.dumps(row))


if __name__ == "__main__":
    main()
