#!/usr/bin/env python3
"""Project-local current-identity c8/c16/c32 adapter for the retained vLLM controller."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
CAMPAIGN = PROJECT.parents[2] / "campaign_100"
NEBIUS = CAMPAIGN / "nebius"
MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
TOKENIZER_HASHES = {
    "353a3ff93723c098ac93fb593d4d1b93faede916fe502b005cd503871023e012",
    "b6b807f7bfaf4fb4bd3952f58a70d61442620df8e5d8a904dcf4bc6ca7946940",
    "d63ad536c3c81880043e22ec7fd08db42b4d8fb7c89c7138bc562bfa25281375",
}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def transformed_remote() -> str:
    source = (NEBIUS / "remote_vllm_awq_smoke.sh").read_text()
    replacements = {
        "19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d": "353a3ff93723c098ac93fb593d4d1b93faede916fe502b005cd503871023e012",
        "31a173e2797ddc8b72ac996803513e627fc28d7aad02cfcce321a431d865c86d": "b6b807f7bfaf4fb4bd3952f58a70d61442620df8e5d8a904dcf4bc6ca7946940",
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise RuntimeError(f"expected exactly one frozen hash: {old}")
        source = source.replace(old, new)
    return source


def transformed_runner() -> str:
    source = (NEBIUS / "vllm_batched_runner.py").read_text()
    old = "if values not in {(1, 8), (1, 8, 16)}:\n        raise BatchError(\"concurrencies must be the fixed c1,c8 control or c1,c8,c16 frontier\")"
    new = "if values not in {(1, 8), (1, 8, 16), (1, 8, 16, 32)}:\n        raise BatchError(\"concurrencies must be the fixed c1,c8 control or adjacent c16/c32 frontier\")"
    if source.count(old) != 1:
        raise RuntimeError("runner frontier contract changed unexpectedly")
    return source.replace(old, new)


def write_staging(root: Path) -> dict:
    stage = root / "nebius"
    stage.mkdir()
    (stage / "remote_vllm_awq_smoke.sh").write_text(transformed_remote())
    (stage / "vllm_batched_runner.py").write_text(transformed_runner())
    for name in ("vllm_decode_kernel_patch.py", "vllm_preflight.py"):
        shutil.copy2(NEBIUS / name, stage / name)
    (root / "quality").symlink_to(CAMPAIGN / "quality", target_is_directory=True)
    (root / "allocations").symlink_to(CAMPAIGN / "allocations", target_is_directory=True)
    rows = []
    for path in sorted(stage.iterdir()):
        rows.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    result = {"current_tokenizer_hashes": sorted(TOKENIZER_HASHES), "staged_files": rows}
    (root / "staging-manifest.json").write_bytes(canonical(result) + b"\n")
    return result


def validate_frontier(values: tuple[int, ...], max_num_seqs: int) -> tuple[int, ...]:
    if values not in {(1, 8), (1, 8, 16), (1, 8, 16, 32)}:
        raise RuntimeError("frontier must be c1,c8 with adjacent c16/c32 steps")
    if max_num_seqs < max(values):
        raise RuntimeError("max_num_seqs cannot admit requested frontier")
    return values


def redact(text: str) -> str:
    return re.sub(r"(?i)((?:authorization|api[_-]?key|token|secret)\s*[:=]\s*)[^\s]+", r"\1[REDACTED]", text)


def write_create_diagnostic(output_dir: Path, result: subprocess.CompletedProcess) -> dict:
    stdout = str(result.stdout or "")
    stderr = str(result.stderr or "")
    value = {
        "stage": "provider_create",
        "returncode": int(result.returncode),
        "stdout": redact(stdout[:16384]),
        "stderr": redact(stderr[:16384]),
        "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
        "truncated": len(stdout) > 16384 or len(stderr) > 16384,
    }
    (output_dir / "provider-create-diagnostic.json").write_bytes(canonical(value) + b"\n")
    return value


def is_create_command(command: object) -> bool:
    return isinstance(command, list) and "instance" in command and "create" in command


def run(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(NEBIUS))
    import vllm_smoke_control as control

    values = validate_frontier(tuple(int(value) for value in args.frontier_concurrencies.split(",")), args.max_num_seqs)
    with tempfile.TemporaryDirectory(prefix="glm47-current-awq-v2-") as raw:
        root = Path(raw)
        manifest = write_staging(root)
        (args.output_dir / "v2-staging-manifest.json").write_bytes(canonical(manifest) + b"\n")
        original_here = control.HERE
        original_validate = control.validate_frontier_concurrencies
        original_run = control.subprocess.run

        def observed_run(command, *values, **kwargs):
            result = original_run(command, *values, **kwargs)
            if is_create_command(command):
                write_create_diagnostic(args.output_dir, result)
            return result

        control.HERE = root / "nebius"
        control.validate_frontier_concurrencies = validate_frontier
        control.subprocess.run = observed_run
        try:
            return control.run(
                args.output_dir, args.name, args.ssh_key, args.ssh_public_key, MODEL, MODEL,
                args.experiment_spec_sha256, False, args.num_kv_splits, args.max_num_seqs, values,
                args.absolute_timeout_seconds,
            )
        finally:
            control.HERE = original_here
            control.validate_frontier_concurrencies = original_validate
            control.subprocess.run = original_run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name")
    parser.add_argument("--ssh-key", type=Path)
    parser.add_argument("--ssh-public-key", type=Path)
    parser.add_argument("--experiment-spec-sha256")
    parser.add_argument("--num-kv-splits", type=int, choices=(4, 8, 16), default=4)
    parser.add_argument("--max-num-seqs", type=int, choices=(8, 16, 32), default=32)
    parser.add_argument("--frontier-concurrencies", default="1,8,16,32")
    parser.add_argument("--absolute-timeout-seconds", type=int, default=2700)
    parser.add_argument("--fixture-create-diagnostic", action="store_true")
    args = parser.parse_args()
    if args.fixture_create_diagnostic:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.CompletedProcess(["fixture", "instance", "create"], 3, "capacity token=fixture", "quota exhausted")
        write_create_diagnostic(args.output_dir, result)
        return 0
    if not all((args.name, args.ssh_key, args.ssh_public_key, args.experiment_spec_sha256)):
        parser.error("--name, --ssh-key, --ssh-public-key, and --experiment-spec-sha256 are required")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
