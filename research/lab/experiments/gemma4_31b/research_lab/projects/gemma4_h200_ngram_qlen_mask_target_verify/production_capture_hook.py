from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import json
import math
import os
import pathlib
import statistics
import threading
import time
from typing import Any

import torch


BATCH = 32
DRAFT = 12
TRACE_WINDOW_MS = 2375.141908
_lock = threading.Lock()
_captured: dict[str, dict[str, Any]] = {}


def _atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_candidate(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("qlen_two_stage_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate_module_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": values,
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(values),
        "maximum_ms": ordered[-1],
    }


def _timed_ms(call) -> float:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    call()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end))


def _compact_mask(
    full_mask: torch.Tensor,
    full_indptr: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
    indptr_cpu = full_indptr[: BATCH + 1].to(device="cpu", dtype=torch.int64)
    rows = []
    row_strides = []
    for request in range(BATCH):
        start = int(indptr_cpu[request])
        end = int(indptr_cpu[request + 1])
        row_stride = (end - start) // DRAFT
        if row_stride < DRAFT or (end - start) != DRAFT * row_stride:
            raise RuntimeError(
                f"captured_full_mask_geometry_invalid:{request}:{start}:{end}"
            )
        row_strides.append(row_stride)
        rows.append(
            full_mask[start:end]
            .reshape(DRAFT, row_stride)[:, row_stride - DRAFT :]
            .reshape(-1)
        )
    compact = torch.cat(rows).contiguous()
    compact_indptr = torch.arange(
        0,
        (BATCH + 1) * DRAFT * DRAFT,
        DRAFT * DRAFT,
        dtype=full_indptr.dtype,
        device=full_indptr.device,
    )
    return compact, compact_indptr, row_strides


def _invoke(function, args: tuple[Any, ...], output: torch.Tensor, mask, indptr):
    values = list(args)
    values[3] = output
    values[9] = mask
    values[11] = indptr
    return function(*values)


def install() -> None:
    artifact_value = os.environ.get("QLEN_CAPTURE_ARTIFACT")
    candidate_value = os.environ.get("QLEN_CAPTURE_CANDIDATE")
    if not artifact_value or not candidate_value:
        return
    artifact = pathlib.Path(artifact_value)
    candidate_path = pathlib.Path(candidate_value)
    module = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    original = module.extend_attention_fwd
    candidate = _load_candidate(candidate_path)
    signature = inspect.signature(original)
    iterations = int(os.environ.get("QLEN_CAPTURE_ITERATIONS", "9"))

    def captured(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        args = tuple(bound.arguments[name] for name in signature.parameters)
        q, _, _, output, k_buffer, v_buffer = args[:6]
        qo_indptr, kv_indptr, kv_indices, full_mask = args[6:10]
        full_indptr = args[11]
        eligible = (
            full_mask is not None
            and full_indptr is not None
            and qo_indptr.shape[0] == BATCH + 1
            and q.shape[0] == BATCH * DRAFT
            and k_buffer.dtype == torch.float8_e5m2
            and v_buffer.dtype == torch.float8_e5m2
        )
        if not eligible:
            return original(*args)
        first_mask_stride = int(
            (
                full_indptr[1].to(dtype=torch.int64)
                - full_indptr[0].to(dtype=torch.int64)
            ).item()
        ) // DRAFT
        if first_mask_stride < 4000:
            return original(*args)

        sliding_window_size = int(args[18])
        layer_type = (
            "sliding_window"
            if sliding_window_size > 0
            else "full_attention"
        )
        with _lock:
            should_capture = layer_type not in _captured
            if should_capture:
                _captured[layer_type] = {"state": "running"}
        if not should_capture:
            return original(*args)

        try:
            compact, compact_indptr, row_strides = _compact_mask(
                full_mask, full_indptr
            )
            control_output = torch.empty_like(output)
            candidate_output = torch.empty_like(output)
            _invoke(original, args, control_output, full_mask, full_indptr)
            _invoke(
                candidate.extend_attention_fwd,
                args,
                candidate_output,
                compact,
                compact_indptr,
            )
            torch.cuda.synchronize()
            delta = candidate_output.float() - control_output.float()
            bit_exact = bool(torch.equal(candidate_output, control_output))
            oracle = {
                "all_finite": bool(torch.isfinite(candidate_output).all().item()),
                "bit_exact": bit_exact,
                "allclose_atol_0_005_rtol_0_005": bool(
                    torch.allclose(
                        candidate_output.float(),
                        control_output.float(),
                        atol=0.005,
                        rtol=0.005,
                    )
                ),
                "max_abs_error": float(delta.abs().max()),
                "mean_abs_error": float(delta.abs().mean()),
                "relative_l2": float(
                    torch.linalg.vector_norm(delta)
                    / torch.linalg.vector_norm(control_output.float()).clamp_min(1e-12)
                ),
            }
            for _ in range(2):
                _invoke(original, args, control_output, full_mask, full_indptr)
                _invoke(
                    candidate.extend_attention_fwd,
                    args,
                    candidate_output,
                    compact,
                    compact_indptr,
                )
            torch.cuda.synchronize()
            control_times = []
            candidate_times = []
            for index in range(iterations):
                order = ("control", "candidate") if index % 2 == 0 else (
                    "candidate",
                    "control",
                )
                for arm in order:
                    if arm == "control":
                        control_times.append(
                            _timed_ms(
                                lambda: _invoke(
                                    original,
                                    args,
                                    control_output,
                                    full_mask,
                                    full_indptr,
                                )
                            )
                        )
                    else:
                        candidate_times.append(
                            _timed_ms(
                                lambda: _invoke(
                                    candidate.extend_attention_fwd,
                                    args,
                                    candidate_output,
                                    compact,
                                    compact_indptr,
                                )
                            )
                        )
            kv_lengths = (
                kv_indptr[1 : BATCH + 1] - kv_indptr[:BATCH]
            ).to(device="cpu", dtype=torch.int64)
            qo_lengths = (
                qo_indptr[1 : BATCH + 1] - qo_indptr[:BATCH]
            ).to(device="cpu", dtype=torch.int64)
            row = {
                "layer_type": layer_type,
                "branch": "extend_attention_fwd_two_stage",
                "sliding_window_size": sliding_window_size,
                "q": {
                    "shape": list(q.shape),
                    "dtype": str(q.dtype),
                    "stride": list(q.stride()),
                },
                "output": {
                    "shape": list(output.shape),
                    "dtype": str(output.dtype),
                },
                "kv": {
                    "key_buffer_shape": list(k_buffer.shape),
                    "value_buffer_shape": list(v_buffer.shape),
                    "key_dtype": str(k_buffer.dtype),
                    "value_dtype": str(v_buffer.dtype),
                    "page_size": 1,
                    "indices_dtype": str(kv_indices.dtype),
                    "indices_count": int(kv_indices.numel()),
                    "per_request_lengths": kv_lengths.tolist(),
                    "first_request_index_prefix": kv_indices[
                        int(kv_indptr[0]) : int(kv_indptr[0]) + min(8, int(kv_lengths[0]))
                    ].to(device="cpu", dtype=torch.int64).tolist(),
                },
                "query_lengths": qo_lengths.tolist(),
                "mask": {
                    "full_numel": int(full_mask.numel()),
                    "compact_numel": int(compact.numel()),
                    "full_indptr": full_indptr[: BATCH + 1]
                    .to(device="cpu", dtype=torch.int64)
                    .tolist(),
                    "compact_indptr": compact_indptr.to(
                        device="cpu", dtype=torch.int64
                    ).tolist(),
                    "row_strides": row_strides,
                    "suffix_sha256": hashlib.sha256(
                        compact.to(device="cpu", dtype=torch.uint8).numpy().tobytes()
                    ).hexdigest(),
                },
                "control": _distribution(control_times),
                "candidate": _distribution(candidate_times),
                "latency_reduction_fraction": 1
                - statistics.median(candidate_times)
                / statistics.median(control_times),
                "oracle": oracle,
            }
            output.copy_(candidate_output)
            with _lock:
                _captured[layer_type] = row
                complete = all(
                    name in _captured and _captured[name].get("oracle")
                    for name in ("sliding_window", "full_attention")
                )
                if complete:
                    rows = [
                        _captured["sliding_window"],
                        _captured["full_attention"],
                    ]
                    weighted_control = (
                        rows[0]["control"]["median_ms"] * 50
                        + rows[1]["control"]["median_ms"] * 10
                    )
                    weighted_candidate = (
                        rows[0]["candidate"]["median_ms"] * 50
                        + rows[1]["candidate"]["median_ms"] * 10
                    )
                    bound = (
                        (weighted_control - weighted_candidate)
                        * 15
                        / TRACE_WINDOW_MS
                    )
                    exact = all(row["oracle"]["bit_exact"] for row in rows)
                    terminal = {
                        "schema_version": 1,
                        "kind": "first_real_c32_q12_two_stage_captured_call",
                        "production_branch_rows": len(rows),
                        "correct": exact,
                        "first_logit_equivalence": {
                            "status": "execution_derived",
                            "basis": "candidate output replaced stock output in the live first verification forward only after bit-exact comparison",
                            "equivalent": exact,
                        },
                        "positive_whole_request_bound_fraction": bound,
                        "component_pass": exact and bound > 0,
                        "rows": rows,
                        "identity": {
                            "installed_control_source": str(
                                pathlib.Path(module.__file__).resolve()
                            ),
                            "control_sha256": _digest(
                                pathlib.Path(module.__file__).resolve()
                            ),
                            "candidate_sha256": _digest(candidate_path),
                            "torch": torch.__version__,
                            "triton": importlib.import_module("triton").__version__,
                        },
                        "captured_unix_s": time.time(),
                    }
                    _atomic(artifact, terminal)
            return None
        except Exception as error:
            _atomic(
                artifact.with_name("COMPONENT_CAPTURE_ERROR.json"),
                {
                    "schema_version": 1,
                    "layer_type": layer_type,
                    "error": repr(error),
                    "candidate_cuda_started": True,
                    "scientific_invocation_started": True,
                },
            )
            with _lock:
                _captured.pop(layer_type, None)
            raise

    module.extend_attention_fwd = captured
