from __future__ import annotations

import json
import math
import os
import pathlib
import time

import torch
from torch.nn import Parameter

import qserve_sm89
from sglang.srt.layers.quantization.base_config import QuantizeMethodBase
from sglang.srt.layers.quantization import fp8 as fp8_module
from sglang.srt.layers.quantization import fp8_utils
from sglang.srt.layers.quantization.fp8_kernel import (
    sglang_per_token_quant_fp8,
)
from sglang.srt.models import gemma4_causal


HIDDEN = 5376
INTERMEDIATE = 21504
GATE_UP = 43008
GROUP_SIZE = 128
MAX_STAGE2 = 18
CACHE = pathlib.Path(
    os.environ.get("QSERVE_W4_CACHE", "/work/w4_cache")
)
EVENTS = pathlib.Path(
    os.environ.get("QSERVE_EVENT_LOG", "/work/artifacts/qserve-events.jsonl")
)


def append_event(event: str, **fields: object) -> None:
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a") as handle:
        handle.write(
            json.dumps(
                {"epoch": time.time(), "event": event, **fields},
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()


def pack_codes(codes: torch.Tensor) -> torch.Tensor:
    output_features, input_features = codes.shape
    reordered = (
        codes.reshape(
            output_features // 32,
            2,
            2,
            8,
            input_features // 32,
            2,
            4,
            4,
        )
        .permute(0, 4, 3, 6, 1, 5, 2, 7)
        .contiguous()
        .permute(0, 1, 2, 3, 5, 6, 7, 4)
        .contiguous()
    )
    packed = (
        (reordered[..., 1].to(torch.int16) << 4)
        | reordered[..., 0].to(torch.int16)
    )
    return (
        packed.to(torch.uint8)
        .view(torch.int8)
        .reshape(output_features, input_features // 2)
    )


def reorder_metadata(tensor: torch.Tensor) -> torch.Tensor:
    output_features, groups = tensor.shape
    return (
        tensor.transpose(0, 1)
        .contiguous()
        .reshape(groups, output_features // 32, 4, 8)
        .transpose(-2, -1)
        .contiguous()
        .reshape(groups, output_features)
    )


def fp8_weight(weight: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    transposed = weight.to(torch.bfloat16).t().contiguous()
    scale = (
        transposed.float()
        .abs()
        .amax(dim=0)
        .div(448.0)
        .clamp_min(1e-8)
        .float()
    )
    return (transposed / scale).to(torch.float8_e4m3fn), scale


def progressive_pack(
    weight: torch.Tensor,
) -> tuple[dict[str, torch.Tensor], dict[str, float]]:
    rows, columns = weight.shape
    qweight = torch.empty(
        (rows, columns // 2), device=weight.device, dtype=torch.int8
    )
    groups = columns // GROUP_SIZE
    scales_i8 = torch.empty(
        (groups, rows), device=weight.device, dtype=torch.int8
    )
    zeros = torch.empty_like(scales_i8)
    weight_scales = torch.empty(
        (rows,), device=weight.device, dtype=torch.float16
    )
    squared_error = 0.0
    squared_reference = 0.0
    maximum_absolute = 0.0
    for start in range(0, rows, 512):
        stop = min(start + 512, rows)
        block = weight[start:stop].float().reshape(
            stop - start, groups, GROUP_SIZE
        )
        group_scale = block.abs().amax(dim=2).div(7.0)
        base = (
            group_scale.amax(dim=1)
            .div(float(MAX_STAGE2))
            .clamp_min(torch.finfo(torch.float16).tiny)
        )
        stage2 = (
            torch.round(group_scale / base[:, None])
            .clamp(1, MAX_STAGE2)
            .to(torch.int8)
        )
        effective = base[:, None] * stage2.float()
        codes = (
            torch.round(block / effective[:, :, None])
            .add(7)
            .clamp(0, 15)
            .to(torch.int8)
            .reshape(stop - start, columns)
        )
        reconstructed = (
            (codes.reshape(stop - start, groups, GROUP_SIZE).float() - 7.0)
            * effective[:, :, None]
        )
        delta = reconstructed - block
        squared_error += float(delta.square().sum())
        squared_reference += float(block.square().sum())
        maximum_absolute = max(maximum_absolute, float(delta.abs().max()))
        qweight[start:stop].copy_(pack_codes(codes))
        reordered = reorder_metadata(stage2)
        scales_i8[:, start:stop].copy_(reordered)
        zeros[:, start:stop].copy_(
            (-7 * reordered.to(torch.int16)).to(torch.int8)
        )
        weight_scales[start:stop].copy_(base.to(torch.float16))
    return (
        {
            "qweight": qweight,
            "scales_i8": scales_i8,
            "zeros": zeros,
            "weight_scales": weight_scales,
        },
        {
            "relative_l2": math.sqrt(squared_error / squared_reference),
            "maximum_absolute": maximum_absolute,
        },
    )


class QServeLinearMethod(QuantizeMethodBase):
    def __init__(self, prefix: str, kind: str):
        self.prefix = prefix
        self.kind = kind
        self.cache_paths: dict[int, pathlib.Path] = {}
        self.workspaces: dict[int, dict[str, torch.Tensor]] = {}
        self.logged_decode = False
        self.logged_prefill = False

    def create_weights(
        self,
        layer: torch.nn.Module,
        input_size_per_partition: int,
        output_partition_sizes: list[int],
        input_size: int,
        output_size: int,
        params_dtype: torch.dtype,
        **_: object,
    ) -> None:
        output_size_per_partition = sum(output_partition_sizes)
        weight = Parameter(
            torch.empty(
                output_size_per_partition,
                input_size_per_partition // 2,
                dtype=torch.int8,
            ),
            requires_grad=False,
        )
        weight.output_dim = 0
        weight.input_dim = 1
        weight.weight_loader = (
            lambda parameter, loaded_weight, loaded_shard_id=None: self.weight_loader(
                layer,
                parameter,
                loaded_weight,
                loaded_shard_id,
            )
        )
        layer.register_parameter("weight", weight)
        layer.register_buffer(
            "qserve_zeros",
            torch.empty(
                input_size_per_partition // GROUP_SIZE,
                output_size_per_partition,
                dtype=torch.int8,
            ),
            persistent=False,
        )
        layer.register_buffer(
            "qserve_scales_i8",
            torch.empty_like(layer.qserve_zeros),
            persistent=False,
        )
        layer.register_buffer(
            "qserve_weight_scales",
            torch.empty(output_size_per_partition, dtype=torch.float16),
            persistent=False,
        )
        layer.qserve_prefix = self.prefix
        layer.qserve_kind = self.kind

    def cache_path(self, shard_id: int) -> pathlib.Path:
        safe = self.prefix.replace(".", "__")
        return CACHE / f"{safe}__shard{shard_id}.pt"

    def weight_loader(
        self,
        module: torch.nn.Module,
        parameter: Parameter,
        loaded_weight: torch.Tensor,
        loaded_shard_id: int | None = None,
    ) -> None:
        shard_id = int(loaded_shard_id or 0)
        output_size = loaded_weight.shape[0]
        output_offset = shard_id * output_size if self.kind == "gate_up" else 0
        cache_path = self.cache_path(shard_id)
        self.cache_paths[shard_id] = cache_path
        if cache_path.is_file():
            cached = torch.load(cache_path, map_location=parameter.device)
            packed = cached["packed"]
            stats = cached["stats"]
        else:
            source = loaded_weight.to(
                device=parameter.device,
                dtype=torch.bfloat16,
            )
            packed, stats = progressive_pack(source)
            prefill_weight, prefill_scale = fp8_weight(source)
            cached = {
                "schema_version": 1,
                "prefix": self.prefix,
                "shard_id": shard_id,
                "packed": {
                    name: value.cpu() for name, value in packed.items()
                },
                "prefill_weight": prefill_weight.cpu(),
                "prefill_scale": prefill_scale.cpu(),
                "stats": stats,
            }
            CACHE.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(".pt.part")
            torch.save(cached, temporary)
            os.replace(temporary, cache_path)
            del prefill_weight, prefill_scale, source
        parameter.data[
            output_offset : output_offset + output_size
        ].copy_(packed["qweight"])
        module.qserve_scales_i8[
            :, output_offset : output_offset + output_size
        ].copy_(packed["scales_i8"])
        module.qserve_zeros[
            :, output_offset : output_offset + output_size
        ].copy_(packed["zeros"])
        module.qserve_weight_scales[
            output_offset : output_offset + output_size
        ].copy_(packed["weight_scales"])
        append_event(
            "exact_weight_shard_packed",
            prefix=self.prefix,
            shard_id=shard_id,
            rows=output_size,
            columns=int(loaded_weight.shape[1]),
            cache=str(cache_path),
            **stats,
        )

    def process_weights_after_loading(self, layer: torch.nn.Module) -> None:
        return

    def decode_workspace(
        self,
        layer: torch.nn.Module,
        rows: int,
    ) -> dict[str, torch.Tensor]:
        workspace = self.workspaces.get(rows)
        output_features = layer.weight.shape[0]
        if workspace is None:
            workspace = {
                "xq": torch.empty(
                    (rows, layer.weight.shape[1] * 2),
                    device=layer.weight.device,
                    dtype=torch.int8,
                ),
                "xs": torch.empty(
                    (rows,), device=layer.weight.device, dtype=torch.float16
                ),
                "output": torch.empty(
                    (rows, output_features),
                    device=layer.weight.device,
                    dtype=torch.bfloat16,
                ),
            }
            self.workspaces[rows] = workspace
        return workspace

    def decode(self, layer: torch.nn.Module, x: torch.Tensor) -> torch.Tensor:
        rows = x.shape[0]
        workspace = self.decode_workspace(layer, rows)
        qserve_sm89.quantize_bf16_s8(
            x, workspace["xq"], workspace["xs"]
        )
        return self.decode_quantized(
            layer,
            workspace["xq"],
            workspace["xs"],
            workspace["output"],
        )

    def decode_quantized(
        self,
        layer: torch.nn.Module,
        xq: torch.Tensor,
        xs: torch.Tensor,
        output: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if output is None:
            output = self.decode_workspace(layer, xq.shape[0])["output"]
        qserve_sm89.w4a8_gemm(
            xq,
            layer.weight,
            layer.qserve_zeros,
            layer.qserve_scales_i8,
            layer.qserve_weight_scales,
            xs,
            output,
        )
        if not self.logged_decode:
            append_event(
                "candidate_decode_path",
                prefix=self.prefix,
                rows=int(xq.shape[0]),
                output_dtype=str(output.dtype),
            )
            self.logged_decode = True
        return output

    def prefill(self, layer: torch.nn.Module, x: torch.Tensor) -> torch.Tensor:
        shards = []
        scales = []
        for shard_id in sorted(self.cache_paths):
            cached = torch.load(
                self.cache_paths[shard_id],
                map_location="cpu",
                weights_only=True,
            )
            shards.append(cached["prefill_weight"].to(x.device))
            scales.append(cached["prefill_scale"].to(x.device))
        weight = torch.cat(shards, dim=1)
        weight_scale = torch.cat(scales)
        xq, xs = sglang_per_token_quant_fp8(x)
        output = fp8_utils.fp8_scaled_mm(
            xq,
            weight,
            xs,
            weight_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )
        if not self.logged_prefill:
            append_event(
                "fp8_prefill_fallback",
                prefix=self.prefix,
                rows=int(x.shape[0]),
            )
            self.logged_prefill = True
        del shards, scales, weight, weight_scale, xq, xs
        return output

    def apply(
        self,
        layer: torch.nn.Module,
        x: torch.Tensor,
        bias: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if bias is not None:
            raise RuntimeError("qserve_mlp_bias_is_not_supported")
        flattened = x.reshape(-1, x.shape[-1])
        output = (
            self.decode(layer, flattened)
            if flattened.shape[0] <= 32
            else self.prefill(layer, flattened)
        )
        return output.reshape(*x.shape[:-1], output.shape[-1])


original_get_quant_method = fp8_module.Fp8Config.get_quant_method


def get_quant_method(self, layer: torch.nn.Module, prefix: str):
    input_size = getattr(layer, "input_size", None)
    output_size = getattr(layer, "output_size", None)
    if (input_size, output_size) == (HIDDEN, GATE_UP):
        return QServeLinearMethod(prefix, "gate_up")
    if (input_size, output_size) == (INTERMEDIATE, HIDDEN):
        return QServeLinearMethod(prefix, "down")
    return original_get_quant_method(self, layer, prefix)


fp8_module.Fp8Config.get_quant_method = get_quant_method
original_mlp_forward = gemma4_causal.Gemma4MLP.forward


def qserve_mlp_forward(self, x: torch.Tensor) -> torch.Tensor:
    gate_method = self.gate_up_proj.quant_method
    down_method = self.down_proj.quant_method
    if not isinstance(gate_method, QServeLinearMethod) or not isinstance(
        down_method, QServeLinearMethod
    ):
        return original_mlp_forward(self, x)
    flattened = x.reshape(-1, x.shape[-1])
    if flattened.shape[0] > 32:
        gate_up = gate_method.prefill(self.gate_up_proj, flattened)
        activated = self.act_fn(gate_up)
        output = down_method.prefill(self.down_proj, activated)
    else:
        gate_up = gate_method.decode(self.gate_up_proj, flattened)
        rows = flattened.shape[0]
        down_workspace = down_method.decode_workspace(
            self.down_proj, rows
        )
        qserve_sm89.gelu_mul_quant_bf16_s8(
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
    return output.reshape(*x.shape[:-1], output.shape[-1])


gemma4_causal.Gemma4MLP.forward = qserve_mlp_forward
append_event("qserve_runtime_overlay_installed")
