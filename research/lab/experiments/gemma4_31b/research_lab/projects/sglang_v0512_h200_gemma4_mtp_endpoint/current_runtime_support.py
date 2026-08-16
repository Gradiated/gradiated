#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import struct
import subprocess
import sys


SGLANG_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
SGLANG_TAG_OBJECT = "cba18f4d8090d23e9273e663db2a0b3b2e39f117"
SGLANG_IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
TRANSFORMERS_VERSION = "5.8.1"
ASSISTANT_REVISION = "627c5ec1458b9086b841a91e0512fd31fd2fbbf1"
TARGET_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def safetensors_header(path: pathlib.Path) -> dict[str, object]:
    with path.open("rb") as handle:
        size = struct.unpack("<Q", handle.read(8))[0]
        return json.loads(handle.read(size))


def has_class(path: pathlib.Path, name: str) -> bool:
    return any(
        isinstance(node, ast.ClassDef) and node.name == name
        for node in ast.walk(ast.parse(path.read_text()))
    )


def parse_configs(target: pathlib.Path, assistant: pathlib.Path) -> dict[str, object]:
    program = """
import json,sys,transformers
from transformers import AutoConfig
rows=[]
for label,path in [('target',sys.argv[1]),('assistant',sys.argv[2])]:
    cfg=AutoConfig.from_pretrained(path,local_files_only=True)
    rows.append({'label':label,'class':type(cfg).__name__,'model_type':cfg.model_type,'architectures':cfg.architectures})
print(json.dumps({'transformers_version':transformers.__version__,'rows':rows},sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(target), str(assistant)],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(f"config_consumer_failed:{result.stderr[-2000:]}")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-source", type=pathlib.Path, required=True)
    parser.add_argument("--target", type=pathlib.Path, required=True)
    parser.add_argument("--assistant", type=pathlib.Path, required=True)
    parser.add_argument("--assistant-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source = args.sglang_source.resolve()
    target = args.target.resolve()
    assistant = args.assistant.resolve()
    observed_commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    if observed_commit != SGLANG_COMMIT:
        raise RuntimeError(f"sglang_commit_mismatch:{observed_commit}")

    assistant_terminal = json.loads(args.assistant_terminal.read_text())
    expected_assistant = {row["name"]: row for row in assistant_terminal["files"]}
    observed_assistant = {
        name: {"bytes": (assistant / name).stat().st_size, "sha256": sha256(assistant / name)}
        for name in expected_assistant
    }
    if any(
        observed_assistant[name] != {"bytes": row["bytes"], "sha256": row["sha256"]}
        for name, row in expected_assistant.items()
    ):
        raise RuntimeError("assistant_content_mismatch")

    target_config = json.loads((target / "config.json").read_text())
    assistant_config = json.loads((assistant / "config.json").read_text())
    target_text = target_config["text_config"]
    assistant_text = assistant_config["text_config"]
    geometry_pass = bool(
        target_config["model_type"] == "gemma4"
        and assistant_config["model_type"] == "gemma4_assistant"
        and assistant_config["backbone_hidden_size"] == target_text["hidden_size"] == 5376
        and assistant_text["hidden_size"] == 1024
        and assistant_text["num_hidden_layers"] == 4
        and assistant_text["num_kv_shared_layers"] == 4
        and assistant_text["vocab_size"] == target_text["vocab_size"] == 262144
        and set(assistant_text["layer_types"]).issubset(set(target_text["layer_types"]))
    )

    relative_sources = [
        "python/pyproject.toml",
        "python/sglang/srt/arg_groups/speculative_hook.py",
        "python/sglang/srt/layers/quantization/fp8.py",
        "python/sglang/srt/layers/quantization/fp8_utils.py",
        "python/sglang/srt/models/gemma4_mtp.py",
        "python/sglang/srt/speculative/frozen_kv_mtp_worker.py",
        "python/sglang/srt/speculative/frozen_kv_mtp_utils.py",
        "python/sglang/srt/server_args.py",
    ]
    source_hashes = {name: sha256(source / name) for name in relative_sources}
    mtp_model = source / "python/sglang/srt/models/gemma4_mtp.py"
    spec_hook_text = (source / "python/sglang/srt/arg_groups/speculative_hook.py").read_text()
    server_args_text = (source / "python/sglang/srt/server_args.py").read_text()
    fp8_text = (source / "python/sglang/srt/layers/quantization/fp8.py").read_text()
    runtime_mechanism_pass = bool(
        has_class(mtp_model, "Gemma4AssistantForCausalLM")
        and "FROZEN_KV_MTP" in spec_hook_text
        and "Gemma4AssistantForCausalLM" in spec_hook_text
        and "self.speculative_draft_model_quantization = self.quantization" in server_args_text
        and "SGLANG_FP8_IGNORED_LAYERS" in fp8_text
        and "if not self.is_checkpoint_fp8_serialized" in fp8_text
        and "return apply_fp8_linear(" in fp8_text
        and '"transformers==5.8.1"' in (source / "python/pyproject.toml").read_text()
    )

    config_consumer = parse_configs(target, assistant)
    expected_config_rows = [
        {
            "label": "target",
            "class": "Gemma4Config",
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
        },
        {
            "label": "assistant",
            "class": "Gemma4AssistantConfig",
            "model_type": "gemma4_assistant",
            "architectures": ["Gemma4AssistantForCausalLM"],
        },
    ]
    config_consumer_pass = bool(
        config_consumer["transformers_version"] == TRANSFORMERS_VERSION
        and config_consumer["rows"] == expected_config_rows
    )

    header = safetensors_header(assistant / "model.safetensors")
    tensor_keys = sorted(key for key in header if key != "__metadata__")
    assistant_weights_pass = bool(
        len(tensor_keys) == 48
        and "pre_projection.weight" in tensor_keys
        and "post_projection.weight" in tensor_keys
        and "model.embed_tokens.weight" in tensor_keys
    )
    passed = bool(
        geometry_pass
        and runtime_mechanism_pass
        and config_consumer_pass
        and assistant_weights_pass
    )
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "current_runtime_support_pass" if passed else "runtime_unavailable",
        "pass": passed,
        "claim_authorized_by_support": passed,
        "runtime": {
            "sglang_tag": "v0.5.13",
            "sglang_tag_object": SGLANG_TAG_OBJECT,
            "sglang_commit": observed_commit,
            "image_linux_amd64": SGLANG_IMAGE,
            "transformers": TRANSFORMERS_VERSION,
            "source_sha256": source_hashes,
        },
        "identities": {
            "target_revision": TARGET_REVISION,
            "target_config_sha256": sha256(target / "config.json"),
            "assistant_revision": ASSISTANT_REVISION,
            "assistant_files": observed_assistant,
        },
        "geometry": {
            "pass": geometry_pass,
            "target_hidden_size": target_text["hidden_size"],
            "target_layers": target_text["num_hidden_layers"],
            "assistant_hidden_size": assistant_text["hidden_size"],
            "assistant_layers": assistant_text["num_hidden_layers"],
            "assistant_kv_shared_layers": assistant_text["num_kv_shared_layers"],
        },
        "config_consumer": {**config_consumer, "pass": config_consumer_pass},
        "assistant_weights": {
            "pass": assistant_weights_pass,
            "tensor_count": len(tensor_keys),
            "tensor_keys_sha256": hashlib.sha256("\n".join(tensor_keys).encode()).hexdigest(),
        },
        "mechanism": {
            "pass": runtime_mechanism_pass,
            "algorithm": "FROZEN_KV_MTP",
            "proposal_contract": {
                "speculative_num_steps": 1,
                "speculative_eagle_topk": 1,
                "speculative_num_draft_tokens": 2,
                "proposed_tokens_per_verify": 1,
            },
            "target_quantization": "dynamic in-memory FP8 via Fp8Config(is_checkpoint_fp8_serialized=False)",
            "draft_quantization": "inherits target fp8 unless explicitly overridden",
            "kv_contract": "assistant reads target-owned frozen KV and suppresses assistant KV writes",
            "gpu_execution_equivalent_gate_remaining": "load exact target and assistant together, prove target-prefixed fp8_scaled_mm consumption, then run paired endpoint arms",
        },
    }
    atomic(args.output, terminal)
    return 0 if passed else 72


if __name__ == "__main__":
    raise SystemExit(main())
