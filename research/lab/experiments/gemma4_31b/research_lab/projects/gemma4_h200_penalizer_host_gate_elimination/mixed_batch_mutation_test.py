from __future__ import annotations

import json
import pathlib
import types

import torch

from sglang.srt.sampling.penaltylib.min_new_tokens import (
    BatchedMinNewTokensPenalizer,
)


class Orchestrator:
    def __init__(self, reqs, vocab_size=17):
        self._reqs = reqs
        self.vocab_size = vocab_size
        self.device = "cuda"

    def reqs(self):
        return self._reqs


def request(rid: str, minimum: int, eos: int, extra: set[int]):
    sampling = types.SimpleNamespace(
        min_new_tokens=minimum,
        stop_token_ids=set(),
    )
    tokenizer = types.SimpleNamespace(
        eos_token_id=eos,
        additional_stop_token_ids=extra,
    )
    return types.SimpleNamespace(rid=rid, sampling_params=sampling, tokenizer=tokenizer)


def expected(reqs, counts, vocab_size):
    value = torch.zeros((len(reqs), vocab_size), device="cuda")
    for row, req in enumerate(reqs):
        if counts[req.rid] < req.sampling_params.min_new_tokens:
            for token in {req.tokenizer.eos_token_id} | req.tokenizer.additional_stop_token_ids:
                value[row, token] = float("-inf")
    return value


def assert_apply(penalizer, orchestrator, counts):
    logits = torch.zeros(
        (len(orchestrator.reqs()), orchestrator.vocab_size), device="cuda"
    )
    penalizer.apply(logits)
    reference = expected(orchestrator.reqs(), counts, orchestrator.vocab_size)
    assert torch.equal(logits, reference)


def main(output: pathlib.Path) -> None:
    reqs = [
        request("never", 0, 2, {3}),
        request("short", 2, 4, set()),
        request("long", 4, 5, {6}),
    ]
    orchestrator = Orchestrator(reqs)
    penalizer = BatchedMinNewTokensPenalizer(orchestrator)
    penalizer.prepare()
    counts = {req.rid: 0 for req in reqs}
    assert_apply(penalizer, orchestrator, counts)
    for _ in range(2):
        penalizer.cumulate_output_tokens(torch.zeros(len(reqs), dtype=torch.int64, device="cuda"))
        counts = {rid: value + 1 for rid, value in counts.items()}
        assert_apply(penalizer, orchestrator, counts)

    keep = [reqs[2], reqs[0]]
    orchestrator._reqs = keep
    penalizer.filter(torch.tensor([2, 0], dtype=torch.int64, device="cuda"))
    assert_apply(penalizer, orchestrator, counts)

    their_reqs = [request("merged-active", 3, 7, {8}), request("merged-off", 0, 9, set())]
    their_orchestrator = Orchestrator(their_reqs)
    their = BatchedMinNewTokensPenalizer(their_orchestrator)
    their.prepare()
    their_counts = {req.rid: 0 for req in their_reqs}
    their.cumulate_output_tokens(torch.zeros(2, dtype=torch.int64, device="cuda"))
    their_counts = {rid: value + 1 for rid, value in their_counts.items()}

    penalizer.merge(their)
    orchestrator._reqs.extend(their_reqs)
    counts.update(their_counts)
    assert_apply(penalizer, orchestrator, counts)
    for _ in range(3):
        penalizer.cumulate_output_tokens(
            torch.zeros(len(orchestrator.reqs()), dtype=torch.int64, device="cuda")
        )
        counts = {rid: value + 1 for rid, value in counts.items()}
        assert_apply(penalizer, orchestrator, counts)

    result = {
        "schema_version": 1,
        "pass": True,
        "device": torch.cuda.get_device_name(),
        "cases": [
            "mixed_required_not_required",
            "host_counter_transitions",
            "filter_reorder",
            "merge_different_progress",
            "all_inactive_skip",
        ],
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    main(args.output)
