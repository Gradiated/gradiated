#!/usr/bin/env python3

from __future__ import annotations

import dataclasses
import gc
import hashlib
import json
import math
import pathlib
import sys
import types
import weakref


class Matrix:
    def __init__(
        self,
        values,
        dtype,
        shape,
        stride,
        pointer,
        *,
        device="cuda:0",
    ):
        self.values = [list(row) for row in values]
        self.dtype = dtype
        self.shape = shape
        self._stride = stride
        self._pointer = pointer
        self.device = device
        self.is_cuda = device.startswith("cuda")

    def stride(self):
        return self._stride

    def is_contiguous(self):
        return self._stride == (self.shape[-1], 1)

    def data_ptr(self):
        return self._pointer


class TorchStub(types.ModuleType):
    bfloat16 = "torch.bfloat16"
    float32 = "torch.float32"
    float = float32
    Tensor = Matrix
    cuda = types.SimpleNamespace(
        is_available=lambda: False,
        is_current_stream_capturing=lambda: False,
    )


torch = TorchStub("torch")
sys.modules.setdefault("torch", torch)

from grouped_lm_head import (
    BATCH,
    DEPTHS,
    HIDDEN,
    VOCAB,
    dispatch_target_get_logits,
    grouped_buffer_direct_blocker,
    grouped_get_logits_buffer_direct,
)


FIXTURE_VOCAB = 8
SOFTCAP = 30.0


@dataclasses.dataclass
class ForwardMode:
    target_verify: bool = True

    def is_target_verify(self) -> bool:
        return self.target_verify


@dataclasses.dataclass
class Metadata:
    forward_mode: ForwardMode
    next_token_logits_buffer: Matrix | None


def projection_row(row: int) -> list[float]:
    request, depth = divmod(row, DEPTHS)
    unrounded = [
        (request - 15.5) * 0.25
        + (depth - 5.5) * 0.5
        + column * 1.75
        - ((row + column) % 3) * 0.125
        for column in range(FIXTURE_VOCAB)
    ]
    return [round(value * 16.0) / 16.0 for value in unrounded]


def softcap_in_place(logits: Matrix, cap: float) -> None:
    assert cap == SOFTCAP
    logits.values = [
        [cap * math.tanh(value / cap) for value in row] for row in logits.values
    ]


def target_ids(logits: Matrix) -> list[list[int]]:
    rows = [max(range(len(row)), key=row.__getitem__) for row in logits.values]
    return [
        rows[request * DEPTHS : (request + 1) * DEPTHS]
        for request in range(BATCH)
    ]


def accepted_prefixes(targets: list[list[int]]) -> list[int]:
    proposals = [list(row) for row in targets]
    for request in range(BATCH):
        proposals[request][5] = (proposals[request][5] + 1) % FIXTURE_VOCAB
    return [
        next(
            (
                depth
                for depth in range(DEPTHS)
                if proposals[request][depth] != targets[request][depth]
            ),
            DEPTHS,
        )
        for request in range(BATCH)
    ]


def value_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent
    output_path = root / "artifacts/GROUPED_LM_HEAD_GRAPH_SAFE_BUFFER_FIXTURE.json"
    hidden_states = Matrix(
        [[float(row)] for row in range(BATCH * DEPTHS)],
        torch.bfloat16,
        (BATCH * DEPTHS, HIDDEN),
        (HIDDEN, 1),
        0x1000,
    )
    weight = Matrix(
        [],
        torch.bfloat16,
        (VOCAB, HIDDEN),
        (HIDDEN, 1),
        0x2000,
    )
    buffer = Matrix(
        [[-1.0] * FIXTURE_VOCAB for _ in range(BATCH * DEPTHS)],
        torch.float32,
        (BATCH * DEPTHS, VOCAB),
        (VOCAB, 1),
        0x3000,
    )
    buffer_reference = weakref.ref(buffer)
    buffer_contract_before = {
        "data_ptr": buffer.data_ptr(),
        "dtype": buffer.dtype,
        "shape": list(buffer.shape),
        "stride": list(buffer.stride()),
        "device": buffer.device,
    }
    metadata = Metadata(ForwardMode(), buffer)
    processor = types.SimpleNamespace(
        use_fp32_lm_head=False,
        logit_scale=None,
        do_tensor_parallel_all_gather=False,
        do_tensor_parallel_all_gather_dp_attn=False,
        final_logit_softcapping=SOFTCAP,
    )
    lm_head = types.SimpleNamespace(weight=weight)
    launch_rows = []
    launch_invocations = []
    depth_program_order = []
    softcap_objects = []

    def fixture_kernel(hidden, tied_weight, output):
        launch_invocations.append("depth_interleaved_grouped_lm_head")
        assert hidden is hidden_states
        assert tied_weight is weight
        assert output is buffer
        for vocab_block in range((VOCAB + 255) // 256):
            del vocab_block
            for depth in range(DEPTHS):
                depth_program_order.append(depth)
        for request in range(BATCH):
            for depth in range(DEPTHS):
                row = request * DEPTHS + depth
                launch_rows.append((request, depth, row))
                output.values[row] = projection_row(row)

    def fixture_softcap(logits, cap):
        softcap_objects.append((logits is buffer, logits.data_ptr()))
        softcap_in_place(logits, cap)

    candidate_calls = []
    stock_calls = []

    def candidate_projector(_processor, _hidden, _lm_head, _metadata):
        candidate_calls.append("grouped_get_logits_buffer_direct")
        return grouped_get_logits_buffer_direct(
            _processor,
            _hidden,
            _lm_head,
            _metadata,
            kernel_launcher=fixture_kernel,
            softcap_operator=fixture_softcap,
        )

    def stock_must_not_run(*_args):
        stock_calls.append("stock")
        raise AssertionError("captured buffered fixture fell back to stock")

    blocker = grouped_buffer_direct_blocker(
        processor, hidden_states, lm_head, metadata, None
    )
    repaired = dispatch_target_get_logits(
        stock_must_not_run,
        processor,
        hidden_states,
        lm_head,
        metadata,
        None,
        capture_active=True,
        grouped_projector=stock_must_not_run,
        buffer_projector=candidate_projector,
    )
    buffer_contract_after = {
        "data_ptr": repaired.data_ptr(),
        "dtype": repaired.dtype,
        "shape": list(repaired.shape),
        "stride": list(repaired.stride()),
        "device": repaired.device,
    }

    stock_oracle = Matrix(
        [projection_row(row) for row in range(BATCH * DEPTHS)],
        torch.float32,
        (BATCH * DEPTHS, VOCAB),
        (VOCAB, 1),
        0x4000,
    )
    softcap_in_place(stock_oracle, SOFTCAP)
    candidate_targets = target_ids(repaired)
    stock_targets = target_ids(stock_oracle)
    candidate_prefixes = accepted_prefixes(candidate_targets)
    stock_prefixes = accepted_prefixes(stock_targets)
    expected_rows = [
        (request, depth, request * DEPTHS + depth)
        for request in range(BATCH)
        for depth in range(DEPTHS)
    ]
    del metadata
    gc.collect()
    checks = {
        "captured_and_buffered_contract_admitted": blocker is None,
        "candidate_path_executed_once": candidate_calls
        == ["grouped_get_logits_buffer_direct"],
        "stock_fallback_not_executed": stock_calls == [],
        "one_grouped_kernel_launch": launch_invocations
        == ["depth_interleaved_grouped_lm_head"],
        "depth_minor_program_order_0_through_11": all(
            depth_program_order[start : start + DEPTHS] == list(range(DEPTHS))
            for start in range(0, len(depth_program_order), DEPTHS)
        ),
        "request_major_row_ownership_exact": launch_rows == expected_rows,
        "live_buffer_object_preserved": repaired is buffer,
        "live_buffer_pointer_preserved": (
            buffer_contract_after["data_ptr"] == buffer_contract_before["data_ptr"]
        ),
        "live_buffer_dtype_shape_stride_preserved": (
            buffer_contract_after == buffer_contract_before
        ),
        "live_buffer_lifetime_preserved": buffer_reference() is buffer,
        "softcap_boundary_used_live_buffer": softcap_objects
        == [(True, buffer.data_ptr())],
        "post_softcap_logits_exact": repaired.values == stock_oracle.values,
        "downstream_target_ids_exact": candidate_targets == stock_targets,
        "downstream_accepted_prefixes_exact": candidate_prefixes == stock_prefixes,
    }
    result = {
        "schema_version": 1,
        "classification": "offline_exact_candidate_path_contract_fixture",
        "evidence_type": "synthetic_source_execution_not_cuda_execution",
        "production_contract": {
            "batch": BATCH,
            "depths": DEPTHS,
            "hidden": HIDDEN,
            "vocab": VOCAB,
            "hidden_dtype": str(hidden_states.dtype),
            "weight_dtype": str(weight.dtype),
            "buffer": buffer_contract_before,
            "cuda_graph_capture_active": True,
            "softcap": SOFTCAP,
        },
        "activation": {
            "buffer_direct_blocker": blocker,
            "candidate_symbol": "grouped_get_logits_buffer_direct",
            "kernel_symbol": "depth_interleaved_grouped_lm_head",
            "candidate_calls": candidate_calls,
            "stock_calls": stock_calls,
        },
        "ordering": {
            "program_order": "vocab_block_major_depth_minor",
            "first_vocab_block_depths": depth_program_order[:DEPTHS],
            "first_request_rows": launch_rows[:DEPTHS],
            "last_request_rows": launch_rows[-DEPTHS:],
        },
        "downstream": {
            "candidate_target_ids_sha256": value_sha256(candidate_targets),
            "stock_target_ids_sha256": value_sha256(stock_targets),
            "candidate_accepted_prefixes_sha256": value_sha256(candidate_prefixes),
            "stock_accepted_prefixes_sha256": value_sha256(stock_prefixes),
            "logits_sha256": value_sha256(repaired.values),
        },
        "checks": checks,
        "pass": all(checks.values()),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(output_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
