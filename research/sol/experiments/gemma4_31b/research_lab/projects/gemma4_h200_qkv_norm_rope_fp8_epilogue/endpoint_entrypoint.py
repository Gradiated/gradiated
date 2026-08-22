#!/usr/bin/env python3
"""Pinned SGLang endpoint entrypoint with the QKV direct-cache patch."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys

from qkv_direct_endpoint_patch import (
    EXPECTED_RADIX_ATTENTION_SHA256,
    EXPECTED_TRITON_BACKEND_SHA256,
    install,
)


SGLANG_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
GEMMA4_SOURCE = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py"
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_and_audit() -> None:
    root = pathlib.Path(os.environ["QKV_ENDPOINT_ARTIFACT_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    os.environ["QKV_DIRECT_PATH_PROOF"] = str(root / "PATH_PROOF.jsonl")
    patch = install(GEMMA4_SOURCE, root / "PATCH_AUDIT.json")

    from sglang.srt.layers import radix_attention
    from sglang.srt.layers.attention import triton_backend

    observed = {
        "radix_attention": sha256(pathlib.Path(radix_attention.__file__)),
        "triton_backend": sha256(pathlib.Path(triton_backend.__file__)),
    }
    expected = {
        "radix_attention": EXPECTED_RADIX_ATTENTION_SHA256,
        "triton_backend": EXPECTED_TRITON_BACKEND_SHA256,
    }
    if observed != expected:
        raise RuntimeError(
            "pinned consumer source mismatch:"
            + json.dumps({"expected": expected, "observed": observed}, sort_keys=True)
        )
    (root / "RUNTIME_IDENTITY.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sglang_commit": SGLANG_COMMIT,
                "consumer_sources": observed,
                "patch": patch,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def audited_scheduler(*args, **kwargs):
    install_and_audit()
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
        launch_server(server_args, run_scheduler_process_func=audited_scheduler)
    finally:
        kill_process_tree(os.getpid(), include_parent=False)


if __name__ == "__main__":
    main()
