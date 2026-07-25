#!/usr/bin/env python3

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import sys
import types


class Matrix:
    def __init__(self, values, dtype, shape=None):
        self.values = [list(row) for row in values]
        self.dtype = dtype
        self.shape = shape or (len(self.values), len(self.values[0]))

    def reshape(self, *shape):
        if shape == (BATCH, DEPTHS, 1):
            return RequestDepthView(self)
        if shape == (BATCH * DEPTHS, 1):
            self.shape = shape
            return self
        raise AssertionError(f"unexpected reshape: {shape}")

    def contiguous(self):
        return self

    def float(self):
        return Matrix(self.values, "torch.float32")

    def to(self, dtype):
        return Matrix(self.values, dtype)

    def tolist(self):
        return [row[0] for row in self.values]

    def copy_(self, other):
        self.values = [list(row) for row in other.values]
        self.shape = other.shape
        return self


class RequestDepthView:
    def __init__(self, matrix):
        self.matrix = matrix

    def __getitem__(self, key):
        rows, depth, features = key
        assert rows == slice(None) and features == slice(None)
        return Matrix(
            [self.matrix.values[request * DEPTHS + depth] for request in range(BATCH)],
            self.matrix.dtype,
        )


class StackedDepths:
    def __init__(self, depths):
        self.depths = depths

    def reshape(self, rows, columns):
        assert (rows, columns) == (BATCH * DEPTHS, 1)
        values = [
            self.depths[depth].values[request]
            for request in range(BATCH)
            for depth in range(DEPTHS)
        ]
        return Matrix(values, self.depths[0].dtype)


class TorchStub(types.ModuleType):
    bfloat16 = "torch.bfloat16"
    float32 = "torch.float32"
    Tensor = Matrix
    cuda = types.SimpleNamespace(
        is_available=lambda: False,
        is_current_stream_capturing=lambda: False,
    )

    @staticmethod
    def stack(values, dim):
        assert dim == 1
        return StackedDepths(values)


torch = TorchStub("torch")
sys.modules.setdefault("torch", torch)

from grouped_lm_head import (
    BATCH,
    DEPTHS,
    HIDDEN,
    VOCAB,
    dispatch_target_get_logits,
    grouped_activation_blocker,
)


@dataclasses.dataclass
class ForwardMode:
    target_verify: bool = True

    def is_target_verify(self) -> bool:
        return self.target_verify


@dataclasses.dataclass
class Metadata:
    forward_mode: ForwardMode
    next_token_logits_buffer: torch.Tensor | None


def tensor_sha256(value: torch.Tensor) -> str:
    return hashlib.sha256(
        json.dumps(value.values, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent
    output_path = root / "artifacts/GROUPED_LM_HEAD_LIVE_CONTRACT_FIXTURE.json"
    hidden_descriptor = types.SimpleNamespace(
        shape=(BATCH * DEPTHS, HIDDEN),
        dtype=torch.bfloat16,
    )
    weight_descriptor = types.SimpleNamespace(
        shape=(VOCAB, HIDDEN),
        dtype=torch.bfloat16,
    )
    processor = types.SimpleNamespace(use_fp32_lm_head=False)
    lm_head_descriptor = types.SimpleNamespace(weight=weight_descriptor)
    buffer_marker = Matrix(
        [[-1] for _ in range(BATCH * DEPTHS)],
        torch.float32,
    )
    live_metadata = Metadata(ForwardMode(), buffer_marker)
    live_blocker = grouped_activation_blocker(
        processor,
        hidden_descriptor,
        lm_head_descriptor,
        live_metadata,
        None,
        capture_active=True,
    )
    capture_only_blocker = grouped_activation_blocker(
        processor,
        hidden_descriptor,
        lm_head_descriptor,
        Metadata(ForwardMode(), None),
        None,
        capture_active=True,
    )
    eager_component_blocker = grouped_activation_blocker(
        processor,
        hidden_descriptor,
        lm_head_descriptor,
        Metadata(ForwardMode(), None),
        None,
        capture_active=False,
    )

    hidden_states = Matrix(
        [[row] for row in range(BATCH * DEPTHS)],
        torch.float32,
    )
    call_rows: list[list[int]] = []

    def stock_projection(
        _processor,
        depth_hidden_states,
        _lm_head,
        metadata,
        _embedding_bias,
    ):
        assert metadata.next_token_logits_buffer is None
        rows = depth_hidden_states.tolist()
        call_rows.append(rows)
        return depth_hidden_states.float()

    def grouped_must_not_run(*_args):
        raise AssertionError("grouped projector crossed the live contract gate")

    repaired = dispatch_target_get_logits(
        stock_projection,
        processor,
        hidden_states,
        lm_head_descriptor,
        live_metadata,
        None,
        capture_active=True,
        grouped_projector=grouped_must_not_run,
    )
    expected_calls = [
        list(range(depth, BATCH * DEPTHS, DEPTHS)) for depth in range(DEPTHS)
    ]
    expected_output = Matrix(
        [[row] for row in range(BATCH * DEPTHS)],
        torch.float32,
    )
    checks = {
        "live_buffer_blocks_candidate": live_blocker == "live_logits_buffer",
        "capture_blocks_candidate_without_buffer": (
            capture_only_blocker == "cuda_graph_capture"
        ),
        "eager_component_still_admitted": eager_component_blocker is None,
        "stock_depth_call_order_exact": call_rows == expected_calls,
        "request_major_output_order_exact": repaired.values == expected_output.values,
        "live_buffer_identity_preserved": repaired is buffer_marker,
        "live_buffer_contents_exact": buffer_marker.values == expected_output.values,
        "production_dispatch_used_stock_fallback": len(call_rows) == DEPTHS,
    }
    result = {
        "schema_version": 1,
        "classification": "offline_exact_live_call_contract_fixture",
        "production_contract": {
            "batch": BATCH,
            "depths": DEPTHS,
            "hidden": HIDDEN,
            "vocab": VOCAB,
            "hidden_shape": list(hidden_descriptor.shape),
            "weight_shape": list(weight_descriptor.shape),
            "hidden_dtype": str(hidden_descriptor.dtype),
            "weight_dtype": str(weight_descriptor.dtype),
            "next_token_logits_buffer_dtype": str(buffer_marker.dtype),
            "cuda_graph_capture": True,
        },
        "activation": {
            "live_contract_blocker": live_blocker,
            "capture_only_blocker": capture_only_blocker,
            "eager_component_blocker": eager_component_blocker,
        },
        "stock_order": {
            "depth_call_count": len(call_rows),
            "rows_per_call": [len(rows) for rows in call_rows],
            "first_row_per_call": [rows[0] for rows in call_rows],
            "last_row_per_call": [rows[-1] for rows in call_rows],
            "output_sha256": tensor_sha256(repaired),
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
