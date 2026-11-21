"""Derive an explicit loader-compatible checkpoint for the measured PEFT key bug."""

import argparse
import copy
import hashlib
import json
import os
import shutil
from pathlib import Path

ORIGINAL_TRAIN_SHA256 = (
    "aaea82ec204cfc3732fc1bc60a83359bd5c36fe11024683fedc9587ed4ad6351"
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--runner-dir", type=Path, required=True)
    parser.add_argument("--output-checkpoint", type=Path, required=True)
    args = parser.parse_args()
    original = json.loads((args.checkpoint / "checkpoint-complete.json").read_text())
    identity = original["identity"]
    sources = identity["executable_sources_sha256"]
    if sources["runner/train.py"] != ORIGINAL_TRAIN_SHA256:
        raise ValueError("this repair supports only the measured frozen2b runner")
    for name, sha in sources.items():
        path = (
            args.source_dir / name.removeprefix("runner/")
            if name.startswith("runner/")
            else args.run_dir / "jevbench" / name
        )
        if digest(path) != sha:
            raise ValueError("origin executable bytes differ: " + name)
    if not {"trainer.pt", "adapter_model.safetensors"} <= set(original["files"]):
        raise ValueError("origin checkpoint lacks mandatory payload hashes")
    for name, sha in original["files"].items():
        if Path(name).name != name or digest(args.checkpoint / name) != sha:
            raise ValueError("origin checkpoint payload differs")
    if args.runner_dir.exists() or args.output_checkpoint.exists():
        raise ValueError("preserve old repairs; destinations must be new")
    shutil.copytree(
        args.source_dir, args.runner_dir, ignore=shutil.ignore_patterns("__pycache__")
    )
    helper = Path(__file__).with_name("adapter_restore.py")
    shutil.copy2(helper, args.runner_dir / helper.name)
    path = args.runner_dir / "train.py"
    source = path.read_text()
    old_call = '        set_peft_model_state_dict(\n            model, load_file(str(ckpt / "adapter_model.safetensors"))\n        )'
    if source.count(old_call) != 1 or source.count('"runtime.py",') != 2:
        raise ValueError("frozen loader structure differs")
    source = source.replace(
        "from data import read_jsonl",
        "from adapter_restore import restore_adapter\nfrom data import read_jsonl",
        1,
    )
    source = source.replace(", set_peft_model_state_dict", "", 1)
    source = source.replace(
        old_call, old_call.replace("set_peft_model_state_dict", "restore_adapter")
    )
    source = source.replace(
        '"runtime.py",', '"runtime.py",\n            "adapter_restore.py",'
    )
    compile(source, str(path), "exec")
    path.write_text(source)
    target_identity = copy.deepcopy(identity)
    target_sources = target_identity["executable_sources_sha256"]
    target_sources["runner/train.py"] = digest(path)
    target_sources["runner/adapter_restore.py"] = digest(args.runner_dir / helper.name)
    differences = {
        name: {"origin": sources.get(name), "resume": target_sources.get(name)}
        for name in set(sources) | set(target_sources)
        if sources.get(name) != target_sources.get(name)
    }
    if set(differences) != {"runner/train.py", "runner/adapter_restore.py"}:
        raise ValueError("repair unexpectedly changes other executable identities")
    assert {
        key: value
        for key, value in identity.items()
        if key != "executable_sources_sha256"
    } == {
        key: value
        for key, value in target_identity.items()
        if key != "executable_sources_sha256"
    }
    proof = {
        "reason": "Measured PEFT0.22 weight_proj rewriting omits16 adapter tensors; exact named-parameter restore changes no forward/loss/optimizer/sampling code.",
        "origin_checkpoint_manifest_sha256": digest(
            args.checkpoint / "checkpoint-complete.json"
        ),
        "origin_checkpoint": str(args.checkpoint.resolve()),
        "source_changes": differences,
        "payloads_sha256": original["files"],
        "model_data_runtime_recipe_unchanged": True,
        "identity_semantics": "Derived identity is the compatible loader requirement, not a claim that the new loader wrote the origin payloads. The target runner must independently match it before loading. Origin writer identity is retained verbatim.",
        "repair_executable_sha256": digest(Path(__file__)),
    }
    derived = {
        **original,
        "identity": target_identity,
        "origin_writer_identity": identity,
        "compatibility_migration": proof,
    }
    args.output_checkpoint.mkdir(parents=True)
    for name in original["files"]:
        os.link(args.checkpoint / name, args.output_checkpoint / name)
    (args.output_checkpoint / "checkpoint-complete.json").write_text(
        json.dumps(derived, indent=2) + "\n"
    )
    (args.runner_dir / "resume-repair.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "runner_dir": str(args.runner_dir),
                "derived_checkpoint": str(args.output_checkpoint),
                "origin_manifest_sha256": proof["origin_checkpoint_manifest_sha256"],
                "derived_manifest_sha256": digest(
                    args.output_checkpoint / "checkpoint-complete.json"
                ),
                "source_changes": differences,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
