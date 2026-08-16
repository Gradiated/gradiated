from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import time

import torch


BASE_OVERLAY = pathlib.Path("/endpoint/sitecustomize.py")
CONTROL = pathlib.Path(
    os.environ.get(
        "QSERVE_TRACE_CONTROL",
        "/work/artifacts/qserve-causal-trace/TRACE_CONTROL.json",
    )
)
TRACE_EVENTS = pathlib.Path(
    os.environ.get(
        "QSERVE_TRACE_EVENTS",
        "/work/artifacts/qserve-causal-trace/trace-events.jsonl",
    )
)
CAPTURE = pathlib.Path(
    os.environ.get(
        "QSERVE_TRACE_CAPTURE",
        "/work/artifacts/qserve-causal-trace/captured-hidden.pt",
    )
)


spec = importlib.util.spec_from_file_location("qserve_base_overlay", BASE_OVERLAY)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load base overlay: {BASE_OVERLAY}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def append_trace(event: str, **fields: object) -> None:
    TRACE_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_EVENTS.open("a") as handle:
        handle.write(
            json.dumps(
                {"epoch": time.time(), "event": event, **fields},
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()


control_cache: tuple[int, dict[str, object]] | None = None
layer_steps: dict[tuple[str, int], int] = {}
captured: set[tuple[str, int, int]] = set()


def trace_control() -> dict[str, object]:
    global control_cache
    try:
        stamp = CONTROL.stat().st_mtime_ns
    except FileNotFoundError:
        return {
            "run_id": "startup",
            "depth": 60,
            "capture_layer": -1,
            "capture_step": -1,
        }
    if control_cache is None or control_cache[0] != stamp:
        value = json.loads(CONTROL.read_text())
        depth = int(value["depth"])
        if depth not in (0, 1, 15, 30, 45, 60):
            raise RuntimeError(f"unfrozen W4 prefix depth: {depth}")
        control_cache = (stamp, value)
    return control_cache[1]


def layer_index(gate_method: object) -> int:
    match = re.search(r"\.layers\.(\d+)\.mlp\.", str(gate_method.prefix))
    if match is None:
        raise RuntimeError(f"cannot parse layer index: {gate_method.prefix}")
    return int(match.group(1))


def maybe_capture(
    x: torch.Tensor,
    control: dict[str, object],
    index: int,
    step: int,
) -> None:
    run_id = str(control["run_id"])
    key = (run_id, index, step)
    if (
        index != int(control.get("capture_layer", -1))
        or step != int(control.get("capture_step", -1))
        or key in captured
    ):
        return
    torch.cuda.synchronize()
    value = {
        "schema_version": 1,
        "run_id": run_id,
        "depth": int(control["depth"]),
        "layer": index,
        "decode_step": step,
        "shape": list(x.shape),
        "dtype": str(x.dtype),
        "x": x.detach().to("cpu"),
    }
    temporary = CAPTURE.with_suffix(".pt.part")
    torch.save(value, temporary)
    os.replace(temporary, CAPTURE)
    captured.add(key)
    append_trace(
        "hidden_state_captured",
        run_id=run_id,
        depth=int(control["depth"]),
        layer=index,
        decode_step=step,
        shape=list(x.shape),
    )


def fp8_control(
    method: base.QServeLinearMethod,
    x: torch.Tensor,
) -> torch.Tensor:
    shards = []
    scales = []
    for shard_id in sorted(method.cache_paths):
        cached = torch.load(
            method.cache_paths[shard_id],
            map_location="cpu",
            weights_only=True,
        )
        shards.append(cached["prefill_weight"].to(x.device))
        scales.append(cached["prefill_scale"].to(x.device))
    # The retained cache was serialized row-major, while fp8_scaled_mm requires
    # its B operand to have column-major strides.
    weight = torch.cat(shards, dim=1).t().contiguous().t()
    weight_scale = torch.cat(scales)
    xq, xs = base.sglang_per_token_quant_fp8(x)
    output = base.fp8_utils.fp8_scaled_mm(
        xq,
        weight,
        xs,
        weight_scale,
        out_dtype=torch.bfloat16,
        bias=None,
    )
    del shards, scales, weight, weight_scale, xq, xs
    return output


def traced_mlp_forward(self, x: torch.Tensor) -> torch.Tensor:
    gate_method = self.gate_up_proj.quant_method
    down_method = self.down_proj.quant_method
    if not isinstance(gate_method, base.QServeLinearMethod) or not isinstance(
        down_method, base.QServeLinearMethod
    ):
        return base.original_mlp_forward(self, x)
    control = trace_control()
    index = layer_index(gate_method)
    run_id = str(control["run_id"])
    depth = int(control["depth"])
    flattened = x.reshape(-1, x.shape[-1])
    if flattened.shape[0] > 32:
        route = "fp8_prefill"
        step = -1
        gate_up = fp8_control(gate_method, flattened)
        activated = self.act_fn(gate_up)
        output = fp8_control(down_method, activated)
    else:
        step_key = (run_id, index)
        step = layer_steps.get(step_key, 0)
        layer_steps[step_key] = step + 1
        maybe_capture(flattened, control, index, step)
        if index < depth:
            route = "w4_decode"
            gate_up = gate_method.decode(self.gate_up_proj, flattened)
            down_workspace = down_method.decode_workspace(
                self.down_proj, flattened.shape[0]
            )
            base.qserve_sm89.gelu_mul_quant_bf16_s8(
                gate_up,
                down_workspace["xq"],
                down_workspace["xs"],
            )
            output = down_method.decode_quantized(
                self.down_proj,
                down_workspace["xq"],
                down_workspace["xs"],
                down_workspace["output"],
            )
        else:
            route = "fp8_decode"
            gate_up = fp8_control(gate_method, flattened)
            activated = self.act_fn(gate_up)
            output = fp8_control(down_method, activated)
    append_trace(
        "layer_route",
        run_id=run_id,
        depth=depth,
        layer=index,
        decode_step=step,
        rows=int(flattened.shape[0]),
        route=route,
    )
    return output.reshape(*x.shape[:-1], output.shape[-1])


base.gemma4_causal.Gemma4MLP.forward = traced_mlp_forward
append_trace("causal_trace_overlay_installed")
