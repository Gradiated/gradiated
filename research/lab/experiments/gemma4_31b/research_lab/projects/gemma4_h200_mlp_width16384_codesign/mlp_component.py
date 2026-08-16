#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics


CONTROL_I = 21504
CANDIDATE_I = 16384
HIDDEN = 5376
M_VALUES = (32, 118, 1409, 1631, 2048)


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(ordered),
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--down-snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--selection", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    state_path = args.output / "INVOCATION_STATE.json"
    atomic(state_path, {"candidate_cuda_started": False, "candidate_science_started": False})

    import torch
    from safetensors import safe_open
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization.fp8_kernel import sglang_per_token_quant_fp8
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    if not torch.cuda.is_available() or "H200" not in torch.cuda.get_device_properties(0).name:
        raise RuntimeError("exact H200 required")
    selection = json.loads(args.selection.read_text())
    selected = torch.tensor(selection["layers"][0]["indices"], dtype=torch.long)
    if selected.numel() != CANDIDATE_I or not bool(torch.all(selected[1:] > selected[:-1])):
        raise RuntimeError("invalid canonical layer0 selection")
    with safe_open(str(args.snapshot), framework="pt", device="cpu") as handle:
        gate = handle.get_tensor("model.language_model.layers.0.mlp.gate_proj.weight")
        up = handle.get_tensor("model.language_model.layers.0.mlp.up_proj.weight")
    with safe_open(str(args.down_snapshot), framework="pt", device="cpu") as handle:
        down = handle.get_tensor("model.language_model.layers.0.mlp.down_proj.weight")
    if tuple(gate.shape) != (CONTROL_I, HIDDEN) or tuple(up.shape) != (CONTROL_I, HIDDEN) or tuple(down.shape) != (HIDDEN, CONTROL_I):
        raise RuntimeError("real weight geometry mismatch")

    def weight(raw):
        bf16 = raw.cuda().t()
        scale = (bf16.float().abs().amax(dim=0) / 448).clamp_min(1e-8).float()
        return (bf16 / scale).to(torch.float8_e4m3fn), scale

    gate_up_control, gate_up_control_scale = weight(torch.cat((gate, up), dim=0))
    gate_up_candidate, gate_up_candidate_scale = weight(
        torch.cat((gate.index_select(0, selected), up.index_select(0, selected)), dim=0)
    )
    down_control, down_control_scale = weight(down)
    down_candidate, down_candidate_scale = weight(down.index_select(1, selected))
    del gate, up, down
    activation = GeluAndMul(approximate="tanh")

    def chain(x, gate_up_weight, gate_up_scale, down_weight, down_scale):
        xq, xs = sglang_per_token_quant_fp8(x)
        gate_up_out = fp8_scaled_mm(xq, gate_up_weight, xs, gate_up_scale, out_dtype=torch.bfloat16)
        activated = activation(gate_up_out)
        aq, a_scale = sglang_per_token_quant_fp8(activated)
        output = fp8_scaled_mm(aq, down_weight, a_scale, down_scale, out_dtype=torch.bfloat16)
        return output

    state = json.loads(state_path.read_text())
    state["candidate_cuda_started"] = True
    atomic(state_path, state)
    torch.manual_seed(20260723)
    rows = []
    for m in M_VALUES:
        x = torch.empty((m, HIDDEN), device="cuda", dtype=torch.bfloat16).normal_(0, 0.7)
        candidate = chain(
            x,
            gate_up_candidate,
            gate_up_candidate_scale,
            down_candidate,
            down_candidate_scale,
        )
        state["candidate_science_started"] = True
        atomic(state_path, state)
        if not bool(torch.isfinite(candidate).all()):
            raise RuntimeError(f"candidate nonfinite at M={m}")
        consumed = float(candidate.float().square().sum().item())
        timings = {}
        for name, values in (
            ("control", (gate_up_control, gate_up_control_scale, down_control, down_control_scale)),
            ("candidate", (gate_up_candidate, gate_up_candidate_scale, down_candidate, down_candidate_scale)),
        ):
            for _ in range(5):
                chain(x, *values)
            torch.cuda.synchronize()
            samples = []
            for _ in range(30):
                start = torch.cuda.Event(enable_timing=True)
                end = torch.cuda.Event(enable_timing=True)
                start.record()
                output = chain(x, *values)
                end.record()
                end.synchronize()
                samples.append(start.elapsed_time(end))
                if not bool(torch.isfinite(output).all()):
                    raise RuntimeError(f"{name} nonfinite at M={m}")
            timings[name] = stats(samples)
        reduction = 1 - timings["candidate"]["median_ms"] / timings["control"]["median_ms"]
        rows.append(
            {
                "m": m,
                "consumer_chain": "per_token_fp8 -> fp8_scaled_mm(gate_up) -> GeluAndMul(tanh) -> per_token_fp8 -> fp8_scaled_mm(down)",
                "control": timings["control"],
                "candidate": timings["candidate"],
                "reduction_fraction": reduction,
                "candidate_output_consumed_sum_squares": consumed,
                "candidate_output_finite": True,
            }
        )
        atomic(args.output / f"ROW_M{m}.json", rows[-1])

    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "component_complete",
        "pass": all(row["reduction_fraction"] > 0 for row in rows),
        "hardware": torch.cuda.get_device_properties(0).name,
        "runtime_consumer": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
        "activation_consumer": "sglang.srt.layers.activation.GeluAndMul",
        "geometry": {
            "hidden": HIDDEN,
            "control_intermediate": CONTROL_I,
            "candidate_intermediate": CANDIDATE_I,
            "control_gate_up": [HIDDEN, 2 * CONTROL_I],
            "candidate_gate_up": [HIDDEN, 2 * CANDIDATE_I],
            "control_down": [CONTROL_I, HIDDEN],
            "candidate_down": [CANDIDATE_I, HIDDEN],
        },
        "selection_sha256": hashlib.sha256(args.selection.read_bytes()).hexdigest(),
        "rows": rows,
        "complete_outputs_consumed": True,
    }
    atomic(args.output / "TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 73


if __name__ == "__main__":
    raise SystemExit(main())
