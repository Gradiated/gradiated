"""Small torchrun boundary: equal batches, collective stop decisions, rank-local RNG."""

import contextlib
import datetime
import os
import random


def rank_batches(rows, batch_size, world_size, rank, seed=20261120):
    if min(batch_size, world_size) < 1 or not 0 <= rank < world_size:
        raise ValueError("invalid distributed batch geometry")
    ordered = sorted(rows, key=lambda row: len(row["ids"]))
    if world_size == 1:
        batches = [
            ordered[i : i + batch_size] for i in range(0, len(ordered), batch_size)
        ]
        random.Random(seed).shuffle(batches)
        return batches, 0
    block_size = batch_size * world_size
    usable = len(ordered) // block_size * block_size
    if not usable:
        raise ValueError("not enough examples for a full distributed batch")
    blocks = list(range(0, usable, block_size))
    random.Random(seed).shuffle(blocks)
    return [
        ordered[offset + rank * batch_size : offset + (rank + 1) * batch_size]
        for offset in blocks
    ], len(ordered) - usable


class DistributedRun:
    def __init__(self, torch, backend="nccl", use_cuda=True):
        self.torch = torch
        self.rank = int(os.environ.get("RANK", "0"))
        self.world_size = int(os.environ.get("WORLD_SIZE", "1"))
        self.local_rank = int(os.environ.get("LOCAL_RANK", "0"))
        self.device = f"cuda:{self.local_rank}" if use_cuda else "cpu"
        self.primary = self.rank == 0
        if use_cuda:
            torch.cuda.set_device(self.local_rank)
        if self.world_size > 1:
            torch.distributed.init_process_group(
                backend=backend, timeout=datetime.timedelta(minutes=45)
            )

    def barrier(self):
        if self.world_size > 1:
            self.torch.distributed.barrier()

    def broadcast(self, value):
        if self.world_size == 1:
            return value
        values = [value if self.primary else None]
        self.torch.distributed.broadcast_object_list(values, src=0)
        return values[0]

    def all(self, value):
        value = self.torch.tensor(int(value), device=self.device)
        if self.world_size > 1:
            self.torch.distributed.all_reduce(
                value, op=self.torch.distributed.ReduceOp.MIN
            )
        return bool(value.item())

    def primary_flag(self, value):
        value = self.torch.tensor(int(value) if self.primary else 0, device=self.device)
        if self.world_size > 1:
            self.torch.distributed.broadcast(value, src=0)
        return bool(value.item())

    def sum(self, value):
        value = self.torch.tensor(value, dtype=self.torch.float64, device=self.device)
        if self.world_size > 1:
            self.torch.distributed.all_reduce(value)
        return value.item()

    def gather(self, value):
        if self.world_size == 1:
            return [value]
        values = [None] * self.world_size if self.primary else None
        self.torch.distributed.gather_object(value, values, dst=0)
        return values

    def wrap(self, model):
        if self.world_size == 1:
            return model
        ids = [self.local_rank] if self.device.startswith("cuda") else None
        return self.torch.nn.parallel.DistributedDataParallel(
            model, device_ids=ids, broadcast_buffers=False, find_unused_parameters=True
        )

    def accumulation(self, model, final_microbatch):
        if self.world_size > 1 and not final_microbatch:
            return model.no_sync()
        return contextlib.nullcontext()

    def close(self):
        if self.world_size > 1:
            self.torch.distributed.destroy_process_group()
