#!/usr/bin/env python3
"""Resumable two-host production pipeline for the bound trained-MTP experiment.

This program is deliberately launched only by ``run_two_bench_owner.py`` after
that owner has atomically claimed both benches.  It obtains connection details
from the current pool records instead of treating a director artifact as a
source of mutable host identity.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from grad_research.gpu_pool import GpuPool


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
PROJECT_ID = "gemma4_trained_mtp_assistant_finetune"
REMOTE_ROOT = "/workspace/gemma4-trained-mtp"
SPECULATORS_COMMIT = "aee3cc9b4ed151ae9ec79befee851757c62b3be9"
TARGET_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
EAGLE3_REVISION = "28a1c8b4bb64dbaee883ba35341841138bdf1fe3"
ASSISTANT_REVISION = "627c5ec1458b9086b841a91e0512fd31fd2fbbf1"
SEED = "20260729"
STAGES = (
    "packet_stage",
    "speculators_checkout",
    "target_stage",
    "regenerate_shards",
    "split",
    "hidden_state_relay",
    "prepare_data",
    "train",
    "holdout",
    "endpoint_arms",
)


class PipelineError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise PipelineError(f"{path} is not a JSON object")
    return value


def marker(root: Path, stage: str) -> Path:
    return root / "stages" / f"{stage}.json"


def completed(root: Path, stage: str) -> bool:
    path = marker(root, stage)
    if not path.is_file():
        return False
    value = load_json(path)
    return value.get("stage") == stage and value.get("completed") is True


def complete(root: Path, stage: str, evidence: dict[str, Any]) -> None:
    payload = {"schema_version": 1, "stage": stage, "completed": True,
               "completed_at_utc": utc_now(), **evidence}
    atomic_json(marker(root, stage), payload)


def require_deadline() -> None:
    raw = os.environ.get("TRAINED_MTP_ABSOLUTE_DEADLINE_UTC")
    if not raw:
        raise PipelineError("TRAINED_MTP_ABSOLUTE_DEADLINE_UTC is required")
    deadline = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if deadline <= dt.datetime.now(dt.UTC) + dt.timedelta(minutes=3):
        raise PipelineError("less than three minutes remain before lifecycle deadline")


def bench_records(binding: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pool = GpuPool(LAB)
    result: dict[str, dict[str, Any]] = {}
    for role in ("target", "trainer"):
        expected = binding["benches"][role]["id"]
        record = pool.show(expected)
        claim = record.get("claim")
        if record.get("status") != "claimed" or not isinstance(claim, dict) or claim.get("project") != PROJECT_ID:
            raise PipelineError(f"{role} bench is not claimed by this project")
        resource = record.get("resource")
        if not isinstance(resource, dict):
            raise PipelineError(f"{role} bench lacks connection record")
        for key in ("public_ipv4", "ssh_user", "ssh_identity_path", "known_hosts_namespace"):
            if not isinstance(resource.get(key), str) or not resource[key]:
                raise PipelineError(f"{role} bench lacks {key}")
        if not Path(resource["ssh_identity_path"]).is_file():
            raise PipelineError(f"{role} SSH identity is unavailable locally")
        result[role] = record
    return result


def ssh_prefix(record: dict[str, Any]) -> list[str]:
    resource = record["resource"]
    return ["ssh", "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}",
            "-i", resource["ssh_identity_path"], f"{resource['ssh_user']}@{resource['public_ipv4']}"]


def remote(record: dict[str, Any], command: str, *, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(ssh_prefix(record) + ["bash", "-lc", shlex.quote(command)], text=True,
                          capture_output=True, timeout=timeout, check=False)


def require_remote(record: dict[str, Any], command: str, *, timeout: float = 600) -> str:
    result = remote(record, command, timeout=timeout)
    if result.returncode:
        raise PipelineError(f"remote command failed ({result.returncode}): {result.stderr[-1500:]}")
    return result.stdout


def ssh_copy(source: Path, record: dict[str, Any], destination: str) -> None:
    resource = record["resource"]
    command = ["scp", "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}",
               "-i", resource["ssh_identity_path"], str(source),
               f"{resource['ssh_user']}@{resource['public_ipv4']}:{destination}"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=1800, check=False)
    if result.returncode:
        raise PipelineError(f"packet transfer failed: {result.stderr[-1500:]}")


def ensure_remote_root(record: dict[str, Any]) -> None:
    require_remote(
        record,
        f"sudo -n install -d -o $(id -u) -g $(id -g) {REMOTE_ROOT}",
    )


def stage_packet(root: Path, records: dict[str, dict[str, Any]]) -> None:
    packet_files = ("hidden_state_relay.py", "split_regenerated_data.py",
                    "speculators_dataset_binding.patch", "speculators_cross_host_file_backend.patch")
    manifest = {name: sha256(PROJECT / name) for name in packet_files}
    packet = root / "packet-manifest.json"
    atomic_json(packet, {"schema_version": 1, "files": manifest})
    for record in records.values():
        ensure_remote_root(record)
        require_remote(record, f"mkdir -p {REMOTE_ROOT}/packet")
        for name in packet_files:
            ssh_copy(PROJECT / name, record, f"{REMOTE_ROOT}/packet/{name}.tmp")
            require_remote(record, f"mv {REMOTE_ROOT}/packet/{name}.tmp {REMOTE_ROOT}/packet/{name}")
        ssh_copy(packet, record, f"{REMOTE_ROOT}/packet/packet-manifest.json.tmp")
        require_remote(record, f"mv {REMOTE_ROOT}/packet/packet-manifest.json.tmp {REMOTE_ROOT}/packet/packet-manifest.json")
    assistant = PROJECT.parent / "sglang_v0512_h200_gemma4_mtp_endpoint" / "artifacts" / "assistant"
    assistant_files = ("config.json", "generation_config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json")
    if not all((assistant / name).is_file() for name in assistant_files):
        raise PipelineError("bound immutable stock assistant is unavailable locally")
    target = records["target"]
    require_remote(target, f"mkdir -p {REMOTE_ROOT}/models/stock-assistant")
    assistant_manifest = {name: sha256(assistant / name) for name in assistant_files}
    for name in assistant_files:
        ssh_copy(assistant / name, target, f"{REMOTE_ROOT}/models/stock-assistant/{name}.tmp")
        require_remote(target, f"mv {REMOTE_ROOT}/models/stock-assistant/{name}.tmp {REMOTE_ROOT}/models/stock-assistant/{name}")
    remote_hash = require_remote(target, f"sha256sum {REMOTE_ROOT}/models/stock-assistant/model.safetensors").split()[0]
    if remote_hash != assistant_manifest["model.safetensors"]:
        raise PipelineError("remote stock assistant hash mismatch")
    complete(root, "packet_stage", {"packet_manifest": str(packet), "packet_manifest_sha256": sha256(packet),
                                     "stock_assistant_manifest": assistant_manifest})


def setup_commands(role: str) -> list[str]:
    base = f"set -euo pipefail; sudo -n install -d -o $(id -u) -g $(id -g) {REMOTE_ROOT}; "
    checkout = (f"if [ ! -d {REMOTE_ROOT}/speculators/.git ]; then git clone https://github.com/vllm-project/speculators.git {REMOTE_ROOT}/speculators; fi; "
                f"git -C {REMOTE_ROOT}/speculators fetch --depth 1 origin {SPECULATORS_COMMIT}; "
                f"git -C {REMOTE_ROOT}/speculators checkout --detach {SPECULATORS_COMMIT}")
    if role == "target":
        model = (f"sudo -n apt-get update && sudo -n apt-get install -y python3-pip && "
                 f"python3 -m pip install --user --break-system-packages --disable-pip-version-check huggingface_hub && "
                 f"python3 -c \"from huggingface_hub import snapshot_download; "
                 f"snapshot_download(repo_id='google/gemma-4-31B-it', revision='{TARGET_REVISION}', local_dir='{REMOTE_ROOT}/models/target')\"")
    else:
        model = (f"sudo -n apt-get update && sudo -n apt-get install -y python3-pip && "
                 f"python3 -m pip install --user --break-system-packages --disable-pip-version-check huggingface_hub && "
                 f"python3 -c \"from huggingface_hub import snapshot_download; "
                 f"snapshot_download(repo_id='RedHatAI/gemma-4-31B-it-speculator.eagle3', revision='{EAGLE3_REVISION}', local_dir='{REMOTE_ROOT}/models/eagle3')\"")
    return [base + checkout, base + model]


def target_server_command() -> str:
    venv = f"{REMOTE_ROOT}/venv"
    wheel_dir = f"{REMOTE_ROOT}/runtime"
    wheel = f"{wheel_dir}/vllm-0.26.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"
    wheel_sha256 = "6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b"
    wheel_url = (
        "https://github.com/vllm-project/vllm/releases/download/v0.26.0/"
        "vllm-0.26.0%2Bcu129-cp38-abi3-manylinux_2_28_x86_64.whl"
    )
    server = (
        f"cd {REMOTE_ROOT}/speculators && nohup {venv}/bin/python scripts/launch_vllm.py "
        f"{REMOTE_ROOT}/models/target --hidden-states-path {REMOTE_ROOT}/hidden_states "
        "--target-layer-ids 2 30 57 -- --host 0.0.0.0 --port 8000 "
        "--gpu-memory-utilization 0.82 --max-model-len 4096 --max-num-seqs 32 --enable-prefix-caching "
        f"> {REMOTE_ROOT}/target-server.log 2>&1 &"
    )
    setup = (
        f"sudo -n apt-get update && sudo -n apt-get install -y python3-venv ninja-build && "
        f"mkdir -p {wheel_dir} && "
        f"if ! test -f {wheel} || ! test \"$(sha256sum {wheel} | cut -d\" \" -f1)\" = {wheel_sha256}; then "
        f"curl --fail --location --retry 3 --output {wheel}.tmp {wheel_url} && "
        f"test \"$(sha256sum {wheel}.tmp | cut -d\" \" -f1)\" = {wheel_sha256} && mv {wheel}.tmp {wheel}; fi && "
        f"test -x {venv}/bin/python || python3 -m venv {venv}; "
        f"{venv}/bin/pip install --disable-pip-version-check --upgrade {wheel} && "
        f"{venv}/bin/pip install --disable-pip-version-check --no-deps {REMOTE_ROOT}/speculators && "
        f"ninja --version && "
        f"{venv}/bin/python -c \"import transformers, vllm; assert vllm.__version__ in ('0.26.0', '0.26.0+cu129')\""
    )
    readiness = (
        "for attempt in $(seq 1 600); do "
        "if curl --fail --silent --show-error http://127.0.0.1:8000/health > /dev/null; then exit 0; fi; "
        "if ! kill -0 \"$server_pid\" 2>/dev/null; then "
        f"tail -n 120 {REMOTE_ROOT}/target-server.log >&2; exit 1; fi; "
        "sleep 2; "
        "done; "
        f"tail -n 120 {REMOTE_ROOT}/target-server.log >&2; exit 1"
    )
    return (
        "set -euo pipefail; "
        f"{setup}; "
        f"curl --fail --silent http://127.0.0.1:8000/health > /dev/null || ({server} server_pid=$!; {readiness})"
    )


def regeneration_command() -> str:
    workspace = f"{REMOTE_ROOT}/speculators"
    output = f"{REMOTE_ROOT}/data/generated"
    venv = f"{REMOTE_ROOT}/venv"
    setup = (
        f"sudo -n apt-get update && sudo -n apt-get install -y python3-venv && "
        f"test -x {venv}/bin/python || python3 -m venv {venv}; "
        f"{venv}/bin/pip install --disable-pip-version-check 'datasets>=4.0.0,<=5.0.0' && "
        f"{venv}/bin/pip install --disable-pip-version-check --no-deps {workspace}/hs_connectors && "
        f"{venv}/bin/pip install --disable-pip-version-check --no-deps {workspace} && "
        f"{venv}/bin/python -c \"import aiohttp, datasets, transformers; from speculators.data_generation import configs, vllm_client\""
    )
    runs = []
    for domain, dataset in (
        ("instruction", "ultrachat"),
        ("reasoning", "gsm8k"),
        ("code", "open-perfectblend"),
        ("tool_use", "hermes-fc"),
    ):
        runs.append(
            f"{venv}/bin/python scripts/response_regeneration/script.py "
            "--endpoint http://127.0.0.1:8000/v1/chat/completions "
            f"--dataset {dataset} --limit 1378 --concurrency 32 --max-tokens 512 "
            "--sampling-params '{\"temperature\":0,\"seed\":20260729}' "
            f"--outfile {output}/{domain}.jsonl --resume"
        )
    return (
        "set -euo pipefail; "
        "curl --fail --silent --show-error http://127.0.0.1:8000/health > /dev/null; "
        f"if [ -d {output} ] && [ -z \"$(find {output} -mindepth 1 -print -quit)\" ]; then "
        f"mv {output} {output}.pre-request-empty-$(date -u +%Y%m%dT%H%M%SZ); fi; "
        f"mkdir -p {output}; "
        f"{setup}; "
        f"cd {workspace}; "
        + "; ".join(runs)
    )


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--repair-patch", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    binding = load_json(args.binding)
    if args.terminal.parent != args.artifact_root:
        raise PipelineError("terminal must be directly under artifact root")
    if args.repair_patch:
        repair = load_json(args.repair_patch)
        stage = repair.get("stage")
        if stage not in STAGES:
            raise PipelineError("repair patch must name one known pipeline stage")
        marker(args.artifact_root, stage).unlink(missing_ok=True)
    if args.validate_only:
        print(json.dumps({"valid": True, "stages": STAGES, "target_revision": TARGET_REVISION,
                          "eagle3_revision": EAGLE3_REVISION, "assistant_revision": ASSISTANT_REVISION}))
        return 0
    if binding.get("project_id") != PROJECT_ID:
        raise PipelineError("binding project mismatch")
    require_deadline()
    records = bench_records(binding)
    root = args.artifact_root
    root.mkdir(parents=True, exist_ok=True)
    if not completed(root, "packet_stage"):
        stage_packet(root, records)
    if not completed(root, "speculators_checkout"):
        for record in records.values():
            require_remote(record, setup_commands("target")[0], timeout=1200)
        complete(root, "speculators_checkout", {"commit": SPECULATORS_COMMIT})
    if not completed(root, "target_stage"):
        require_remote(records["target"], setup_commands("target")[1], timeout=7200)
        require_remote(records["trainer"], setup_commands("trainer")[1], timeout=3600)
        complete(root, "target_stage", {"target_revision": TARGET_REVISION, "eagle3_revision": EAGLE3_REVISION})
    # The remaining remote commands are immutable, command-bound stages.  Each
    # marker prevents a completed producer from being replayed after a consumer repair.
    if not completed(root, "hidden_state_relay"):
        target_server = target_server_command()
        relay = (f"nohup python3 {REMOTE_ROOT}/packet/hidden_state_relay.py --root {REMOTE_ROOT}/hidden_states "
                 f"--host 0.0.0.0 --port 8001 > {REMOTE_ROOT}/hidden-state-relay.log 2>&1 &")
        require_remote(records["target"], target_server)
        require_remote(records["target"], relay)
        complete(root, "hidden_state_relay", {"target_server": target_server, "relay": relay})
    target_host = records["target"]["resource"]["public_ipv4"]
    commands = {
        "regenerate_shards": regeneration_command(),
        "split": "python3 /workspace/gemma4-trained-mtp/packet/split_regenerated_data.py --input-dir /workspace/gemma4-trained-mtp/data/generated --output-dir /workspace/gemma4-trained-mtp/data/split --train-per-source 1250 --holdout-per-source 128 --seed 20260729",
        "prepare_data": "python3 scripts/prepare_data.py --model /workspace/gemma4-trained-mtp/models/target --data /workspace/gemma4-trained-mtp/data/split/train.jsonl --output /workspace/gemma4-trained-mtp/data/prepared/train --max-samples 5000 --seq-length 4096 --seed 20260729 --minimum-valid-tokens 8",
        "train": f"SPECULATORS_HS_RELAY_BASE_URL=http://{target_host}:8001 SPECULATORS_HS_RELAY_REMOTE_ROOT=/workspace/gemma4-trained-mtp/hidden_states CUDA_VISIBLE_DEVICES=0 python3 scripts/train.py --verifier-name-or-path /workspace/gemma4-trained-mtp/models/target --from-pretrained /workspace/gemma4-trained-mtp/models/eagle3 --data-path /workspace/gemma4-trained-mtp/data/prepared/train --hidden-states-path /workspace/gemma4-trained-mtp/trainer_hidden_states --vllm-endpoint http://{target_host}:8000/v1 --save-path /workspace/gemma4-trained-mtp/checkpoints --speculator-type eagle3 --target-layer-ids 2 30 57 --ttt-steps 6 --ttt-step-loss-decay 0.8 --epochs 1 --lr 5e-6 --optimizer adamw --total-seq-len 4096 --train-data-ratio 0.95 --on-missing generate --on-generate delete --request-timeout 180 --max-retries 3 --num-workers 4 --prefetch-factor 2 --checkpoint-freq 1 --save-best --seed 20260729 --hidden-states-dtype bfloat16",
        "holdout": "python3 scripts/evaluate/evaluate.py --target http://127.0.0.1:8000/v1 --output-dir /workspace/gemma4-trained-mtp/results/holdout throughput --dataset /workspace/gemma4-trained-mtp/data/split/holdout.jsonl --max-requests 512 --max-concurrency 32",
    }
    for stage, command in commands.items():
        if completed(root, stage):
            continue
        role = "trainer" if stage == "train" else "target"
        require_remote(records[role], f"cd {REMOTE_ROOT}/speculators && {command}", timeout=7200)
        complete(root, stage, {"command": command, "command_sha256": hashlib.sha256(command.encode()).hexdigest()})
    if not completed(root, "endpoint_arms"):
        promotion_text = require_remote(
            records["target"], f"cat {REMOTE_ROOT}/results/holdout/PROMOTION.json"
        )
        promotion = json.loads(promotion_text)
        if promotion.get("promote_to_endpoint") is not True:
            complete(root, "endpoint_arms", {"skipped": "holdout promotion gate was not met", "promotion": promotion})
        else:
            endpoint = (
                "python3 scripts/evaluate/evaluate.py --target http://127.0.0.1:8000/v1 "
                "--output-dir /workspace/gemma4-trained-mtp/results/endpoint throughput "
                "--dataset /workspace/gemma4-trained-mtp/data/endpoint/c32.jsonl --max-requests 32 --max-concurrency 32"
            )
            require_remote(records["target"], f"cd {REMOTE_ROOT}/speculators && {endpoint}", timeout=7200)
            complete(root, "endpoint_arms", {"command": endpoint, "promotion": promotion,
                                                "command_sha256": hashlib.sha256(endpoint.encode()).hexdigest()})
    atomic_json(args.terminal, {"schema_version": 1, "classification": "trained_checkpoint_and_holdout_terminal",
                                "decision_bearing": True, "completed_at_utc": utc_now(),
                                "required_artifact_hashes": {stage: sha256(marker(root, stage)) for stage in STAGES},
                                "resident_release": {"target": {"condition": "maintenance", "contents": {"checkpoint_revision": TARGET_REVISION}},
                                                     "trainer": {"condition": "maintenance", "contents": {"warm_start_revision": EAGLE3_REVISION}}}})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (PipelineError, subprocess.TimeoutExpired) as error:
        print(f"pipeline error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
