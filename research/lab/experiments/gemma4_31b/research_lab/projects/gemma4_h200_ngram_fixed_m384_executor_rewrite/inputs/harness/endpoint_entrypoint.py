#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys


EXPECTED_FILES = {
    "sglang.srt.entrypoints.http_server": "6cc10fd24f81cf0f25bcd023d013af754cf21e2516f60973ab500ea52b62226e",
    "sglang.srt.layers.quantization.fp8": "c7368db317513e5823283eb5567d15fdb742c3b01a98bfc483cb500291b4285a",
    "sglang.srt.layers.quantization.fp8_utils": "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9",
    "sglang.srt.model_loader.loader": "25d312f7d52a5e54955d8f54e0fc525a20c60c3d17cc4c5ad7386a6d720e2971",
}
SGLANG_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def append(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(
            descriptor,
            (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def metadata(tensor: object) -> object:
    if tensor is None:
        return None
    return {"dtype": str(tensor.dtype), "shape": list(tensor.shape)}


def install_audit() -> None:
    from sglang.srt.entrypoints import http_server
    from sglang.srt.layers.quantization import fp8 as fp8_module
    from sglang.srt.layers.quantization import fp8_utils
    from sglang.srt.layers.quantization.fp8 import Fp8Config, Fp8LinearMethod
    from sglang.srt.model_loader import loader

    module_paths = {
        "sglang.srt.entrypoints.http_server": pathlib.Path(http_server.__file__),
        "sglang.srt.layers.quantization.fp8": pathlib.Path(fp8_module.__file__),
        "sglang.srt.layers.quantization.fp8_utils": pathlib.Path(fp8_utils.__file__),
        "sglang.srt.model_loader.loader": pathlib.Path(loader.__file__),
    }
    observed = {name: sha256(path) for name, path in module_paths.items()}
    if observed != EXPECTED_FILES:
        raise RuntimeError(
            "v0.5.13 source binding mismatch: "
            + json.dumps({"expected": EXPECTED_FILES, "observed": observed}, sort_keys=True)
        )

    module_audit = pathlib.Path(os.environ["FP8_MODULE_AUDIT"])
    consumer_audit = pathlib.Path(os.environ["FP8_CONSUMER_AUDIT"])
    runtime_audit = pathlib.Path(os.environ["FP8_RUNTIME_AUDIT"])
    original_get = Fp8Config.get_quant_method
    original_process = Fp8LinearMethod.process_weights_after_loading
    original_apply = Fp8LinearMethod.apply
    original_scaled_mm = fp8_utils.fp8_scaled_mm
    active_prefix: str | None = None
    observed_consumers: set[str] = set()

    atomic(
        runtime_audit,
        {
            "schema_version": 1,
            "pid": os.getpid(),
            "process_role": "scheduler",
            "sglang_commit": SGLANG_COMMIT,
            "source_sha256": observed,
        },
    )

    def audited_get(self, layer, prefix):
        method = original_get(self, layer, prefix)
        if isinstance(method, Fp8LinearMethod):
            method._bound_prefix = prefix
        return method

    def audited_process(self, layer):
        original_process(self, layer)
        append(
            module_audit,
            {
                "pid": os.getpid(),
                "prefix": getattr(self, "_bound_prefix", None),
                "weight": metadata(layer.weight),
                "weight_scale": metadata(layer.weight_scale),
                "is_checkpoint_fp8_serialized": bool(self.is_checkpoint_fp8_serialized),
            },
        )

    def audited_apply(self, layer, x, bias=None):
        nonlocal active_prefix
        previous = active_prefix
        active_prefix = getattr(self, "_bound_prefix", None)
        try:
            return original_apply(self, layer, x, bias)
        finally:
            active_prefix = previous

    def audited_scaled_mm(*args, **kwargs):
        prefix = active_prefix or "<unbound>"
        if prefix not in observed_consumers:
            append(
                consumer_audit,
                {
                    "pid": os.getpid(),
                    "consumer": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
                    "prefix": prefix,
                    "input": metadata(args[0]),
                    "weight": metadata(args[1]),
                    "input_scale": metadata(args[2]),
                    "weight_scale": metadata(args[3]),
                    "out_dtype": str(kwargs.get("out_dtype")),
                },
            )
            observed_consumers.add(prefix)
        return original_scaled_mm(*args, **kwargs)

    Fp8Config.get_quant_method = audited_get
    Fp8LinearMethod.process_weights_after_loading = audited_process
    Fp8LinearMethod.apply = audited_apply
    fp8_utils.fp8_scaled_mm = audited_scaled_mm

    if os.environ.get("NGRAM_PROFILE_RANGES") == "1":
        from profile_ranges import install

        install()


def audited_run_scheduler_process(*args, **kwargs):
    install_audit()
    from sglang.srt.managers.scheduler import run_scheduler_process

    return run_scheduler_process(*args, **kwargs)


def main() -> None:
    from sglang.srt.entrypoints.http_server import launch_server
    from sglang.srt.plugins import load_plugins
    from sglang.srt.server_args import prepare_server_args
    from sglang.srt.utils import kill_process_tree

    load_plugins()
    server_args = prepare_server_args(sys.argv[1:])
    try:
        launch_server(server_args, run_scheduler_process_func=audited_run_scheduler_process)
    finally:
        kill_process_tree(os.getpid(), include_parent=False)


if __name__ == "__main__":
    main()
