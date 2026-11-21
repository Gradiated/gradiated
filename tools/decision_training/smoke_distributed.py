"""Run under torchrun: compare DDP accumulation/resume against a full-batch oracle."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from distributed import DistributedRun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cuda", action="store_true")
    parser.add_argument("--fail-primary-finalization", action="store_true")
    args = parser.parse_args()
    import torch

    context = DistributedRun(
        torch, backend="nccl" if args.cuda else "gloo", use_cuda=args.cuda
    )
    torch.set_num_threads(1)
    torch.manual_seed(20261120 + context.rank)

    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.layer = torch.nn.Linear(3, 2, bias=False, dtype=torch.float64)
            self.unused = torch.nn.Parameter(torch.ones(1, dtype=torch.float64))
            with torch.no_grad():
                self.layer.weight.copy_(
                    torch.arange(6, dtype=torch.float64).reshape(2, 3) / 10
                )

        def forward(self, value):
            return self.layer(value)

    def data(rank, micro, step):
        x = (
            torch.arange(6, dtype=torch.float64, device=context.device).reshape(2, 3)
            / 10
            + rank / 7
            + micro / 11
            + step / 13
        )
        return x, torch.stack((x[:, 0] - x[:, 1], x[:, 1] + x[:, 2]), dim=1)

    model = Toy().to(context.device)
    reference = copy.deepcopy(model)
    wrapped = context.wrap(model)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)
    oracle_optimizer = torch.optim.SGD(reference.parameters(), lr=0.01, momentum=0.9)

    def update(step):
        optimizer.zero_grad(set_to_none=True)
        for micro in range(2):
            x, y = data(context.rank, micro, step)
            with context.accumulation(wrapped, micro == 1):
                (((wrapped(x) - y) ** 2).mean() / 2).backward()
        optimizer.step()

    def oracle(step):
        oracle_optimizer.zero_grad(set_to_none=True)
        for rank in range(context.world_size):
            for micro in range(2):
                x, y = data(rank, micro, step)
                (((reference(x) - y) ** 2).mean() / (2 * context.world_size)).backward()
        oracle_optimizer.step()

    if context.primary:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    context.barrier()
    update(1)
    oracle(1)
    rank_rng = context.gather(torch.get_rng_state())
    checkpoint = args.output_dir / "cpu-smoke.pt"
    if context.primary:
        torch.save(
            {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "rank_rng": rank_rng,
                "world_size": context.world_size,
            },
            checkpoint,
        )
    context.barrier()
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert context.all(digest == context.broadcast(digest if context.primary else None))
    update(2)
    oracle(2)
    expected_weights = model.layer.weight.detach().clone()
    expected_random = torch.rand(10)
    oracle_delta = (expected_weights - reference.layer.weight).abs().max().item()
    state = torch.load(checkpoint, map_location=context.device, weights_only=False)
    assert state["world_size"] == context.world_size
    model.load_state_dict(state["model"])
    optimizer.load_state_dict(state["optimizer"])
    torch.set_rng_state(state["rank_rng"][context.rank].cpu())
    update(2)
    resume_delta = (model.layer.weight - expected_weights).abs().max().item()
    random_delta = (torch.rand(10) - expected_random).abs().max().item()
    rows = context.gather(
        {
            "rank": context.rank,
            "oracle_max_delta": oracle_delta,
            "resume_max_delta": resume_delta,
            "rng_max_delta": random_delta,
        }
    )
    assert context.all(oracle_delta < 1e-12 and resume_delta == 0 and random_delta == 0)
    primary = context.release_for_primary_only()
    if args.fail_primary_finalization:
        assert not torch.distributed.is_initialized()
        (args.output_dir / f"rank-{context.rank}-released.json").write_text(
            json.dumps({"rank": context.rank, "process_group_released": True})
        )
        if primary:
            raise RuntimeError(
                "injected primary finalization failure after worker release"
            )
        return
    if primary:
        result = {
            "passed": True,
            "world_size": context.world_size,
            "backend": "nccl" if args.cuda else "gloo",
            "checkpoint_sha256": digest,
            "ranks": rows,
            "scope": "Toy accumulation/optimizer/RNG equivalence only; does not validate Inkling GPU memory, numerical behavior or throughput",
        }
        (args.output_dir / "result.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
