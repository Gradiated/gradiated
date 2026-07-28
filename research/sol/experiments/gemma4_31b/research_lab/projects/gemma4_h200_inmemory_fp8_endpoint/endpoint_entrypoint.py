#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import inspect
import json
import os
import pathlib
import sys


CORE_EXPECTED_SOURCE_SHA256 = {
    "Fp8Config.get_quant_method": "74f5590f9ff54a7db3e2beb442935f72001ad224f7ee177868d04e2ae118569e",
    "Fp8LinearMethod.process_weights_after_loading": "2164102004837af5ea082f3fd8c451c49ca84487f56501e3f4f9525c41e06fa8",
    "Fp8LinearMethod.apply": "9163cb8585ee8d4b829de020705070be91110101e3406192fb95ab5d665a7ed8",
    "apply_fp8_linear": "066ab1eb420dd8d06b693398385a842721155900bdeedbe024408b185364b436",
}


def append(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(descriptor, line.encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def source_sha256(value: object) -> str:
    return hashlib.sha256(inspect.getsource(value).encode()).hexdigest()


def tensor_metadata(value: object) -> object:
    if value is None:
        return None
    return {"dtype": str(value.dtype), "shape": list(value.shape)}


def install_audit() -> None:
    from sglang.srt.entrypoints.engine import Engine
    from sglang.srt.entrypoints import http_server
    from sglang.srt.layers.quantization import fp8_utils
    from sglang.srt.layers.quantization.fp8 import Fp8Config, Fp8LinearMethod
    from sglang.srt.model_loader.loader import DefaultModelLoader

    audit = pathlib.Path(os.environ["INMEMORY_FP8_AUDIT"])
    consumer_audit = pathlib.Path(os.environ["INMEMORY_FP8_CONSUMER_AUDIT"])
    runtime_audit = pathlib.Path(os.environ["INMEMORY_FP8_RUNTIME_AUDIT"])
    original_get = Fp8Config.get_quant_method
    original_process = Fp8LinearMethod.process_weights_after_loading
    original_apply = Fp8LinearMethod.apply
    original_apply_fp8_linear = fp8_utils.apply_fp8_linear
    original_scaled_mm = fp8_utils.fp8_scaled_mm
    observed_sources = {
        "Fp8Config.get_quant_method": source_sha256(original_get),
        "Fp8LinearMethod.process_weights_after_loading": source_sha256(original_process),
        "Fp8LinearMethod.apply": source_sha256(original_apply),
        "apply_fp8_linear": source_sha256(original_apply_fp8_linear),
        "DefaultModelLoader.load_weights_and_postprocess": source_sha256(
            DefaultModelLoader.load_weights_and_postprocess
        ),
        "Engine._launch_scheduler_processes": source_sha256(
            Engine._launch_scheduler_processes
        ),
        "http_server.launch_server": source_sha256(http_server.launch_server),
    }
    observed_core_sources = {
        name: observed_sources[name] for name in CORE_EXPECTED_SOURCE_SHA256
    }
    if observed_core_sources != CORE_EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            "pinned SGLang source mismatch: "
            + json.dumps(
                {"expected_core": CORE_EXPECTED_SOURCE_SHA256, "observed": observed_sources},
                sort_keys=True,
            )
        )
    write(
        runtime_audit,
        {
            "pid": os.getpid(),
            "process_role": "scheduler",
            "sglang_commit": "127b9e3283f7c2a43234b852ff5c9f1796d53624",
            "source_sha256": observed_sources,
        },
    )
    consumer_observed = False

    def audited_get(self, layer, prefix):
        method = original_get(self, layer, prefix)
        if isinstance(method, Fp8LinearMethod):
            method._inmemory_fp8_prefix = prefix
        return method

    def audited_process(self, layer):
        original_process(self, layer)
        append(
            audit,
            {
                "prefix": getattr(self, "_inmemory_fp8_prefix", None),
                "method": f"{type(self).__module__}.{type(self).__name__}",
                "weight_dtype": str(layer.weight.dtype),
                "weight_shape": list(layer.weight.shape),
                "weight_scale_dtype": str(layer.weight_scale.dtype),
                "weight_scale_shape": list(layer.weight_scale.shape),
                "cutlass_fp8_supported": bool(self.cutlass_fp8_supported),
                "process_source_sha256": hashlib.sha256(inspect.getsource(original_process).encode()).hexdigest(),
            },
        )

    def audited_scaled_mm(*args, **kwargs):
        nonlocal consumer_observed
        if not consumer_observed:
            append(
                consumer_audit,
                {
                    "pid": os.getpid(),
                    "consumer": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
                    "input": tensor_metadata(args[0]),
                    "weight": tensor_metadata(args[1]),
                    "input_scale": tensor_metadata(args[2]),
                    "weight_scale": tensor_metadata(args[3]),
                    "out_dtype": str(kwargs.get("out_dtype")),
                    "apply_source_sha256": observed_sources["Fp8LinearMethod.apply"],
                    "apply_fp8_linear_source_sha256": observed_sources[
                        "apply_fp8_linear"
                    ],
                },
            )
            consumer_observed = True
        return original_scaled_mm(*args, **kwargs)

    Fp8Config.get_quant_method = audited_get
    Fp8LinearMethod.process_weights_after_loading = audited_process
    fp8_utils.fp8_scaled_mm = audited_scaled_mm


def audited_run_scheduler_process(*args, **kwargs):
    install_audit()
    from sglang.srt.managers.scheduler import run_scheduler_process

    return run_scheduler_process(*args, **kwargs)


def run_server() -> None:
    from sglang.srt.entrypoints.http_server import launch_server
    from sglang.srt.plugins import load_plugins
    from sglang.srt.server_args import prepare_server_args
    from sglang.srt.utils import kill_process_tree

    load_plugins()
    server_args = prepare_server_args(sys.argv[1:])
    try:
        launch_server(
            server_args,
            run_scheduler_process_func=audited_run_scheduler_process,
        )
    finally:
        kill_process_tree(os.getpid(), include_parent=False)


if __name__ == "__main__":
    run_server()
