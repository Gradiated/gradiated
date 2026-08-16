#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
from types import SimpleNamespace

from adaptive_depth_contract import ContractError, ProducerRequest
from endpoint_integration import AdaptiveDepthEndpointLifecycle


ROOT = Path(__file__).resolve().parent
GRAPH_CONTRACT = (
    ROOT
    / "inputs/candidate-v0.5.15/source/python/sglang/srt/model_executor/runner/adaptive_ngram_graph.py"
)
SHAPE_KEY = GRAPH_CONTRACT.with_name("shape_key.py")
NGRAM_INFO = (
    GRAPH_CONTRACT.parents[2] / "speculative/ngram_info.py"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_ngram_info():
    torch = types.ModuleType("torch")

    class Tensor:
        def __init__(self, values, *, dtype="int64", device="cpu"):
            self.values = list(values)
            self.dtype = dtype
            self.device = device

        def __getitem__(self, index):
            if isinstance(index, Tensor):
                return Tensor(
                    [self.values[int(item)] for item in index.values],
                    dtype=self.dtype,
                    device=self.device,
                )
            value = self.values[index]
            return (
                Tensor(value, dtype=self.dtype, device=self.device)
                if isinstance(value, list)
                else value
            )

        def __add__(self, value):
            return Tensor(
                [item + int(value) for item in self.values],
                dtype=self.dtype,
                device=self.device,
            )

        def numel(self):
            return len(self.values)

        def tolist(self):
            return list(self.values)

    def tensor(values, *, dtype="int64", device="cpu"):
        return Tensor(values, dtype=dtype, device=device)

    def arange(start, stop=None, *, dtype="int64", device="cpu"):
        if stop is None:
            start, stop = 0, start
        return Tensor(range(start, stop), dtype=dtype, device=device)

    def cat(values, dim=0):
        first = values[0]
        return Tensor(
            [
                item
                for value in values
                for item in value.values
            ],
            dtype=first.dtype,
            device=first.device,
        )

    def zeros(shape, *, dtype="int64", device="cpu"):
        return Tensor(
            [0] * shape[0], dtype=dtype, device=device
        )

    def cumsum(value, dim=0):
        total = 0
        result = []
        for item in value.values:
            total += item
            result.append(total)
        return Tensor(result, dtype=value.dtype, device=value.device)

    torch.Tensor = Tensor
    torch.tensor = tensor
    torch.arange = arange
    torch.cat = cat
    torch.zeros = zeros
    torch.cumsum = cumsum
    sys.modules["torch"] = torch

    grammar = types.ModuleType(
        "sglang.srt.constrained.base_grammar_backend"
    )
    grammar.BaseGrammarObject = object
    attention = types.ModuleType("sglang.srt.layers.attention.utils")
    attention.create_flashinfer_kv_indices_triton = object()
    spec_info = types.ModuleType("sglang.srt.speculative.spec_info")

    class SpecInput:
        def __init__(self, input_type):
            self.input_type = input_type

    class SpecInputType:
        NGRAM_VERIFY = "ngram_verify"

    spec_info.SpecInput = SpecInput
    spec_info.SpecInputType = SpecInputType
    sys.modules[grammar.__name__] = grammar
    sys.modules[attention.__name__] = attention
    sys.modules[spec_info.__name__] = spec_info
    return torch, load_module("adaptive_ngram_info", NGRAM_INFO)


class Sized:
    def __init__(self, size: int):
        self.size = size

    def numel(self) -> int:
        return self.size


def fake_batch(batch_size: int, depth: int, *, token_count: int | None = None):
    seq_lens = tuple(20 + index for index in range(batch_size))
    tokens = batch_size * depth if token_count is None else token_count
    mask = sum(depth * (seq_len + depth) for seq_len in seq_lens)
    return SimpleNamespace(
        batch_size=batch_size,
        input_ids=Sized(tokens),
        positions=Sized(tokens),
        out_cache_loc=Sized(tokens),
        seq_lens_cpu=seq_lens,
        spec_info=SimpleNamespace(
            draft_token_num=depth,
            custom_mask=Sized(mask),
        ),
    )


def requests(
    count: int, generation: int = 0, namespace: str = "request"
) -> tuple[ProducerRequest, ...]:
    return tuple(
        ProducerRequest(
            rid=f"{namespace}-{index}",
            seq_len=16 + index + generation,
            tail_tokens=(100 + index, 200 + generation, 300 + index),
            prefix_kv=tuple(
                10_000 * (index + 1) + offset
                for offset in range(16 + index + generation)
            ),
            out_cache_base=1_000_000 + 100 * index + 20 * generation,
        )
        for index in range(count)
    )


def accepted_paths(request_ids, depth):
    return {
        rid: tuple(range(1 + (index % min(depth, 4))))
        for index, rid in enumerate(request_ids)
    }


def fail_closed(name, operation):
    try:
        operation()
    except (ContractError, ValueError) as error:
        return {"name": name, "result": "fail_closed", "error": str(error)}
    raise AssertionError(f"fixture_did_not_fail:{name}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    graph = load_module("adaptive_ngram_graph", GRAPH_CONTRACT)
    shape_key = load_module("adaptive_shape_key", SHAPE_KEY)
    depth6_key = shape_key.ShapeKey(size=8, speculative_depth=6)
    stale_depth12_key = shape_key.ShapeKey(size=8, speculative_depth=12)
    assert depth6_key != stale_depth12_key
    captured_graphs = {depth6_key: "depth6", stale_depth12_key: "depth12"}
    assert captured_graphs[depth6_key] == "depth6"
    torch, ngram_info = load_ngram_info()
    carrier = ngram_info.NgramVerifyInput(
        draft_token_num=12,
        new_seq_lens=torch.tensor([10, 20]),
        accept_tokens=torch.arange(24),
        accept_lens=torch.tensor([2, 3]),
        accept_token_offsets=torch.tensor([0, 12, 24]),
    )
    carrier.merge_batch(
        ngram_info.NgramVerifyInput(
            draft_token_num=6,
            new_seq_lens=torch.tensor([30]),
            accept_tokens=torch.arange(100, 106),
            accept_lens=torch.tensor([1]),
            accept_token_offsets=torch.tensor([0, 6]),
        )
    )
    assert carrier.accept_token_offsets.tolist() == [0, 12, 24, 30]
    carrier.filter_batch(torch.tensor([2, 0]))
    assert carrier.accept_token_offsets.tolist() == [0, 6, 18]
    assert carrier.accept_tokens.tolist() == list(range(100, 106)) + list(
        range(12)
    )
    captured = tuple(range(1, 33))
    transition = []
    for batch_size, depth in ((7, 12), (8, 6), (7, 12)):
        identity = graph.runtime_identity(
            fake_batch(batch_size, depth),
            captured_batch_sizes=captured,
        )
        assert identity is not None
        transition.append(
            (
                identity.batch_size,
                identity.speculative_depth,
                identity.num_tokens,
            )
        )
    assert transition == [(7, 12, 84), (8, 6, 48), (7, 12, 84)]

    life = AdaptiveDepthEndpointLifecycle()
    b7 = life.run_cycle(
        requests(7), accepted_paths([f"request-{i}" for i in range(7)], 12)
    )
    b8 = life.run_cycle(
        requests(8, 1),
        accepted_paths([f"request-{i}" for i in range(8)], 6),
    )
    b7_back = life.run_cycle(
        requests(7, 2),
        accepted_paths([f"request-{i}" for i in range(7)], 12),
    )
    assert [b7.graph_key, b8.graph_key, b7_back.graph_key] == [
        (7, 12, 84),
        (8, 6, 48),
        (7, 12, 84),
    ]

    high = requests(8, 3)
    permutation = (7, 0, 6, 1, 5, 2, 4, 3)
    permuted = tuple(high[index] for index in permutation)
    original = life.run_cycle(
        high, accepted_paths([request.rid for request in high], 6)
    )
    reordered = life.run_cycle(
        permuted, accepted_paths([request.rid for request in permuted], 6)
    )
    assert all(
        original.batch.draft_tokens[
            original.batch.request_row_slice(original_index)
        ]
        == reordered.batch.draft_tokens[
            reordered.batch.request_row_slice(permuted_index)
        ]
        for permuted_index, original_index in enumerate(permutation)
    )

    flow = AdaptiveDepthEndpointLifecycle()
    cancelled = flow.run_cycle(
        requests(8, 4),
        accepted_paths([f"request-{i}" for i in range(8)], 6),
        cancelled={"request-2"},
    )
    completed = flow.run_cycle(
        requests(8, 5),
        accepted_paths([f"request-{i}" for i in range(8)], 6),
        completed={"request-0", "request-6"},
    )
    assert cancelled.scheduler_rows["request-2"] == ()
    assert completed.scheduler_rows["request-0"] == ()

    empty_match = flow.run_cycle(
        requests(8, 6), {f"request-{i}": (0,) for i in range(8)}
    )
    partial = flow.run_cycle(
        requests(8, 7),
        {
            f"request-{i}": ((0, 1) if i % 2 else (0,))
            for i in range(8)
        },
    )
    assert all(length == 1 for length in empty_match.carrier.accept_lens)
    assert partial.graph_key == (8, 6, 48)

    slots = AdaptiveDepthEndpointLifecycle()
    slots.run_cycle(
        requests(1, 8, "slot"),
        {"slot-0": (0,)},
        completed={"slot-0"},
    )
    generation = slots.reuse_slot(requests(1, 9, "slot")[0])
    reused = slots.run_cycle(requests(1, 9, "slot"), {"slot-0": (0,)})
    assert generation == 0 and reused.graph_key == (1, 12, 12)

    failures = [
        fail_closed(
            "batch8_depth12_stale_key",
            lambda: graph.AdaptiveNgramGraphIdentity.exact(
                batch_size=8, speculative_depth=12, num_tokens=96
            ),
        ),
        fail_closed(
            "batch7_depth6_stale_key",
            lambda: graph.AdaptiveNgramGraphIdentity.exact(
                batch_size=7, speculative_depth=6, num_tokens=42
            ),
        ),
        fail_closed(
            "depth6_padded_to_depth12",
            lambda: graph.AdaptiveNgramGraphIdentity.exact(
                batch_size=8, speculative_depth=6, num_tokens=96
            ),
        ),
    ]
    runtime_failures = {
        "uncaptured_batch": graph.runtime_identity(
            fake_batch(33, 6), captured_batch_sizes=captured
        ),
        "token_shape": graph.runtime_identity(
            fake_batch(8, 6, token_count=96), captured_batch_sizes=captured
        ),
        "wrong_depth": graph.runtime_identity(
            fake_batch(8, 12), captured_batch_sizes=captured
        ),
    }
    wrong_positions = fake_batch(8, 6)
    wrong_positions.positions = Sized(96)
    runtime_failures["positions_shape"] = graph.runtime_identity(
        wrong_positions, captured_batch_sizes=captured
    )
    stale_mask = fake_batch(8, 6)
    stale_mask.spec_info.custom_mask = Sized(
        sum(12 * (seq_len + 12) for seq_len in stale_mask.seq_lens_cpu)
    )
    runtime_failures["stale_custom_mask"] = graph.runtime_identity(
        stale_mask, captured_batch_sizes=captured
    )
    assert all(value is None for value in runtime_failures.values())

    duplicate = requests(1)[0]
    failures.extend(
        [
            fail_closed(
                "duplicate_request_ownership",
                lambda: slots.run_cycle(
                    (duplicate, duplicate), {"request-0": (0,)}
                ),
            ),
            fail_closed(
                "unknown_completion",
                lambda: slots.run_cycle(
                    requests(1, 10, "fail"),
                    {"fail-0": (0,)},
                    completed={"not-present"},
                ),
            ),
            fail_closed(
                "live_slot_reuse",
                lambda: slots.reuse_slot(requests(1, 11, "slot")[0]),
            ),
        ]
    )

    source_root = ROOT / "inputs/candidate-v0.5.15/source/python/sglang/srt"
    source_assertions = {
        "shape_key_depth": "speculative_depth: Optional[int] = None",
        "runner_exact_identity": "adaptive_ngram_graph_identity_mismatch",
        "runner_exact_batch": "if self.adaptive_ngram_graph:\n            bs = raw_bs",
        "triton_dynamic_depth": "depth = self._target_verify_depth(spec_info)",
        "worker_native_depths": "for depth in (12, 6)",
        "worker_ragged_offsets": "accept_token_offsets=torch.arange(",
    }
    source_text = {
        "shape_key_depth": (
            source_root / "model_executor/runner/shape_key.py"
        ).read_text(),
        "runner_exact_identity": (
            source_root / "model_executor/runner/decode_cuda_graph_runner.py"
        ).read_text(),
        "runner_exact_batch": (
            source_root / "model_executor/runner/decode_cuda_graph_runner.py"
        ).read_text(),
        "triton_dynamic_depth": (
            source_root / "layers/attention/triton_backend.py"
        ).read_text(),
        "worker_native_depths": (
            source_root / "speculative/ngram_worker.py"
        ).read_text(),
        "worker_ragged_offsets": (
            source_root / "speculative/ngram_worker.py"
        ).read_text(),
    }
    assert all(
        needle in source_text[name]
        for name, needle in source_assertions.items()
    )

    result = {
        "schema_version": 1,
        "result": "pass",
        "evidence_label": "deterministic_project_local_state_and_source_fixtures",
        "provider_gpu_seconds": 0,
        "checkpoint_loaded": False,
        "endpoint_requests_submitted": 0,
        "transition": transition,
        "graph_keys": [b7.graph_key, b8.graph_key, b7_back.graph_key],
        "typed_shape_key_distinguishes_depth": True,
        "production_ragged_carrier_filter_merge": "pass",
        "permutation": permutation,
        "cancellation_completion": "pass",
        "empty_partial_matches": "pass",
        "slot_reuse_generation": generation,
        "fail_closed": failures,
        "runtime_fail_closed": sorted(runtime_failures),
        "source_assertions": sorted(source_assertions),
        "source_contract_sha256": sha256(GRAPH_CONTRACT),
    }
    output = ROOT / "ADAPTIVE_DEPTH6_CUDA_GRAPH_FIXTURES.json"
    temporary = output.with_suffix(".json.part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
