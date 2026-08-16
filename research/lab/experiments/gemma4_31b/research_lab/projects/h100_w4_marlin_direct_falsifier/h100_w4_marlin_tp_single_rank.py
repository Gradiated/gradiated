#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import types
from pathlib import Path

import torch
from vllm.config import VllmConfig, set_current_vllm_config
from vllm.distributed.parallel_state import (
    destroy_distributed_environment,
    destroy_model_parallel,
    ensure_model_parallel_initialized,
    get_dp_group,
    get_pp_group,
    get_tp_group,
    init_distributed_environment,
)

import h100_w4_marlin_falsifier as program


MACHETE_KERNEL_SHA256 = "0b043743f0a5c29e47264d95db9964c365bdd02f62453da3479f6383a00a8404"


def machete_runtime_identity(Method, method, quantize_weights, awq_pack):
    observed = original_runtime_identity(Method, method, quantize_weights, awq_pack)
    source = observed["source_sha256"]
    observed["selected_kernel"] = f"{type(method.kernel).__module__}.{type(method.kernel).__name__}.apply_weights"
    observed["raw_symbol"] = "AWQMarlinLinearMethod -> MacheteLinearKernel.apply_weights"
    observed["selected_kernel_from_terminal"] = "vllm.model_executor.kernels.linear.mixed_precision.machete.MacheteLinearKernel.apply_weights"
    observed["pass"] = bool(
        observed["runtime_image"] == program.IMAGE
        and observed["vllm"] == program.VLLM
        and observed["gpu"] == program.GPU
        and observed["capability"] == [9, 0]
        and type(method.kernel).__name__ == "MacheteLinearKernel"
        and source["AWQMarlinLinearMethod"] == program.AWQ_MARLIN_CLASS_SHA256
        and source["selected_kernel"] == MACHETE_KERNEL_SHA256
        and source["vllm._custom_ops.marlin_gemm"] == program.MARLIN_GEMM_WRAPPER_SHA256
        and source["quantize_weights"] == program.QUANTIZE_WEIGHTS_SHA256
        and source["awq_pack"] == program.AWQ_PACK_SHA256
    )
    return observed


original_runtime_identity = program.runtime_identity
program.runtime_identity = machete_runtime_identity


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def context_record() -> dict[str, object]:
    groups = {}
    for name, getter in (("tp", get_tp_group), ("pp", get_pp_group), ("dp", get_dp_group)):
        group = getter()
        groups[name] = {
            "world_size": group.world_size,
            "rank": group.rank,
            "local_rank": group.local_rank,
            "ranks": list(group.ranks),
            "device_backend": str(torch.distributed.get_backend(group.device_group)),
        }
    probe = torch.tensor([17.0], device="cuda")
    torch.distributed.all_reduce(probe, group=get_tp_group().device_group)
    torch.cuda.synchronize()
    return {
        "torch_distributed_initialized": torch.distributed.is_initialized(),
        "world_backend": str(torch.distributed.get_backend()),
        "world_size": torch.distributed.get_world_size(),
        "rank": torch.distributed.get_rank(),
        "cuda_collective_probe": float(probe.item()),
        "tp_pp_dp": [1, 1, 1],
        "rendezvous_scheme": "tcp://127.0.0.1:<ephemeral>",
        "groups": groups,
        "pass": bool(
            torch.distributed.is_initialized()
            and str(torch.distributed.get_backend()) == "nccl"
            and torch.distributed.get_world_size() == 1
            and torch.distributed.get_rank() == 0
            and float(probe.item()) == 17.0
            and all(group["world_size"] == 1 and group["rank"] == 0 and group["local_rank"] == 0 and group["device_backend"] == "nccl" for group in groups.values())
        ),
    }


@contextlib.contextmanager
def single_rank_context():
    previous = {name: os.environ.get(name) for name in ("RANK", "WORLD_SIZE", "LOCAL_RANK")}
    os.environ.update({"RANK": "0", "WORLD_SIZE": "1", "LOCAL_RANK": "0"})
    try:
        torch.cuda.set_device(0)
        config = VllmConfig()
        config.model_config = types.SimpleNamespace(dtype=torch.bfloat16, head_dtype=None, is_moe=False)
        with set_current_vllm_config(config):
            init_distributed_environment(
                world_size=1,
                rank=0,
                distributed_init_method=f"tcp://127.0.0.1:{free_port()}",
                local_rank=0,
                backend="nccl",
            )
            ensure_model_parallel_initialized(1, 1, 1, 1, backend="nccl")
            identity = context_record()
            if not identity["pass"]:
                raise RuntimeError("real single-rank vLLM tensor-parallel context failed")
            yield identity
    finally:
        if torch.distributed.is_initialized():
            destroy_model_parallel()
            destroy_distributed_environment()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def output_path() -> Path:
    return Path(sys.argv[sys.argv.index("--output") + 1])


def main() -> int:
    target = output_path()
    identity = None
    try:
        with single_rank_context() as identity:
            code = program.main()
        result = json.loads(target.read_text())
        result["type"] = "gemma4_h100_exact_shape_awq_machete_w4a16"
        result["selected_kernel"] = "vllm.model_executor.kernels.linear.mixed_precision.machete.MacheteLinearKernel.apply_weights"
        result["machete_terminal_binding"] = {"selected_kernel_source_sha256": MACHETE_KERNEL_SHA256, "prior_terminal_proved_tp_context": True}
        result["tensor_parallel_context"] = identity
        result["pass"] = bool(code == 0 and identity["pass"] and result.get("pass") is True)
        target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 0 if result["pass"] else 1
    except Exception as error:
        result = {"schema_version": 1, "type": "gemma4_h100_exact_shape_awq_marlin_w4a16", "pass": False, "rows": [], "error": {"type": type(error).__name__, "message": str(error)[:4000]}, "tensor_parallel_context": identity}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
