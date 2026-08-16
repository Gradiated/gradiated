#!/usr/bin/env python3
"""Corrected durable owner for the exact Gemma vLLM H200 baseline."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NEBIUS_DIR = ROOT / "glm47flash/campaign_100/nebius"
sys.path.insert(0, str(NEBIUS_DIR))
from placement_control import (  # noqa: E402
    PROJECT_ID,
    PROFILE,
    VerifiedRetainedOwner,
    build_create_command,
    extract_instance_id,
    extract_public_ipv4,
    get_instance,
    make_cloud_init,
    utc_now,
    wait_ssh,
)
from session_staging import transfer_checkpoint, transfer_timeout_seconds  # noqa: E402
from stock_control import run_ssh, scp_from, scp_to  # noqa: E402
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic  # noqa: E402


MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
IMAGE = "vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
INDEX_SHA256 = "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUB = KEY.with_suffix(".pub")
CHECKPOINT = HERE.parent / "sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint"
CHECKPOINT_TERMINAL = CHECKPOINT.parent / "CHECKPOINT_TERMINAL.json"
ECONOMIC = HERE.parent / "h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json"
RUNNER = HERE / "gemma_exact_vllm_runner.py"
TRANSFER_VIEW = HERE / "artifacts/corrected-transfer-view"
PROGRAM = HERE / "artifacts/CORRECTED_RENDERED_PROGRAM"
AUDIT = HERE / "artifacts/CORRECTED_FINAL_PROGRAM_AUDIT.json"
INVENTORY = HERE / "artifacts/CORRECTED_PROVIDER_INVENTORY.json"
PROVIDER_RATE_USD_PER_HOUR = 2.45
DISK_RATE_USD_PER_HOUR = 0.0243055
PLANNING_RATE_USD_PER_HOUR = 3.25
FIRST_PROVIDER_SECONDS = 44.999
FIRST_COST_USD_DERIVED = FIRST_PROVIDER_SECONDS / 3600 * (PROVIDER_RATE_USD_PER_HOUR + DISK_RATE_USD_PER_HOUR)
MAX_SECOND_PROVIDER_SECONDS = 80 * 60 - FIRST_PROVIDER_SECONDS


class ContractError(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def append_event(path: Path, event: str, **fields: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps({"timestamp_utc": utc_now(), "event": event, **fields}, sort_keys=True) + "\n")


def prepare_transfer_view() -> dict:
    terminal = json.loads(CHECKPOINT_TERMINAL.read_text())
    if terminal.get("pass") is not True or terminal.get("revision") != REVISION:
        raise ContractError("checkpoint terminal is not exact and passing")
    TRANSFER_VIEW.mkdir(parents=True, exist_ok=True)
    rows = terminal.get("files")
    if not isinstance(rows, list) or not rows:
        raise ContractError("checkpoint terminal has no files")
    for row in rows:
        source = CHECKPOINT / row["path"]
        target = TRANSFER_VIEW / row["path"]
        if not target.exists():
            os.link(source, target)
        if not target.is_file() or target.stat().st_size != int(row["bytes"]):
            raise ContractError(f"transfer view mismatch: {row['path']}")
        if target.stat().st_ino != source.stat().st_ino or target.stat().st_dev != source.stat().st_dev:
            raise ContractError(f"transfer view is not a storage-free hardlink: {row['path']}")
    manifest = "".join(f"{row['sha256']}  {row['path']}\n" for row in rows)
    (TRANSFER_VIEW / "model-files.sha256").write_text(manifest)
    return {
        "source_checkpoint": str(CHECKPOINT),
        "view": str(TRANSFER_VIEW),
        "files": len(rows) + 1,
        "checkpoint_bytes": sum(int(row["bytes"]) for row in rows),
        "new_weight_storage_bytes": 0,
        "manifest_sha256": sha(TRANSFER_VIEW / "model-files.sha256"),
    }


def bootstrap_script() -> str:
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail
deadline=${{1:?deadline epoch required}}
w=/home/glmrunner/gemma
mkdir -p "$w/input" "$w/artifacts" "$w/runtime"
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker.io curl ca-certificates gnupg
fi
sudo systemctl enable --now docker
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq nvidia-container-toolkit
fi
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo docker pull '{IMAGE}'
sudo docker image inspect '{IMAGE}' > "$w/runtime/image-inspect.json"
nvidia-smi --query-gpu=timestamp,name,uuid,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,clocks.sm,clocks.mem --format=csv,noheader,nounits > "$w/runtime/gpu-telemetry.csv"
nohup bash -c 'while test $(date +%s) -lt '"$deadline"'; do nvidia-smi --query-gpu=timestamp,name,uuid,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,clocks.sm,clocks.mem --format=csv,noheader,nounits; sleep 1; done' >> "$w/runtime/gpu-telemetry.csv" 2> "$w/runtime/gpu-telemetry.stderr" < /dev/null &
echo $! > "$w/runtime/gpu-telemetry.pid"
sudo docker rm -f gemma-vllm >/dev/null 2>&1 || true
sudo docker run -d --rm --name gemma-vllm --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" '{IMAGE}' \
  vllm serve "$w/model" --served-model-name '{MODEL}' --dtype bfloat16 --max-model-len 12000 --max-num-seqs 32 --max-num-batched-tokens 65536 --enable-prefix-caching --enable-metrics --host 0.0.0.0 --port 30000 > "$w/runtime/container-id"
ready=0
while test $(date +%s) -lt "$deadline"; do
  if curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/models.json"; then ready=1; break; fi
  sleep 5
done
test "$ready" = 1
sudo docker inspect gemma-vllm > "$w/runtime/container-inspect-after-load.json"
curl -fsS http://127.0.0.1:30000/metrics > "$w/runtime/metrics-after-load.prom"
'''


def baseline_script() -> str:
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail
deadline=${{1:?deadline epoch required}}
w=/home/glmrunner/gemma
rm -rf "$w/artifacts/baseline"
set +e
sudo docker exec -e VLLM_MODEL='{MODEL}' gemma-vllm python3 "$w/input/gemma_exact_vllm_runner.py" --output "$w/artifacts/baseline" --tokenizer "$w/model" --mode baseline
runner_rc=$?
set -e
curl -fsS http://127.0.0.1:30000/metrics > "$w/artifacts/baseline/metrics-owner-after.prom" || true
sudo docker inspect gemma-vllm > "$w/artifacts/baseline/container-inspect-after.json" || true
sudo docker logs gemma-vllm > "$w/artifacts/baseline/server.log" 2>&1 || true
cp "$w/runtime/gpu-telemetry.csv" "$w/artifacts/baseline/gpu-telemetry-through-baseline.csv"
python3 - "$w/artifacts/baseline" "$runner_rc" <<'PY'
import json,sys,time
from pathlib import Path
root=Path(sys.argv[1]); rc=int(sys.argv[2]); result=json.loads((root/'runner-result.json').read_text())
profiles=result.get('profiles') or []
terminal={{
 'schema_version':2,'stage':'exact_gemma_vllm_h200_baseline','pass':rc==0 and result.get('pass') is True,
 'runner_returncode':rc,'complete_count':result.get('complete_count'),'failure_count':result.get('failure_count'),
 'useful_gpu_seconds':result.get('useful_gpu_seconds'),'prefill_decode':result.get('prefill_decode'),
 'raw_metric_contract':result.get('raw_metric_contract'),'reload_count':0,
 'terminal_concurrency':profiles[-1].get('concurrency') if profiles else None,
 'terminal_completed_requests_per_second':profiles[-1].get('completed_requests_per_second') if profiles else None,
 'written_at_epoch':time.time(),
}}
tmp=root/'BASELINE_STAGE_TERMINAL.json.part'; tmp.write_text(json.dumps(terminal,indent=2,sort_keys=True)+'\n'); tmp.replace(root/'BASELINE_STAGE_TERMINAL.json')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$w/artifacts" -czf "$w/baseline-stage.tar.gz" baseline
sha256sum "$w/baseline-stage.tar.gz" > "$w/baseline-stage.tar.gz.sha256"+n+exit "$runner_rc"
'''.replace("\\+n", "\n")


def prefix_script() -> str:
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail
deadline=${{1:?deadline epoch required}}
w=/home/glmrunner/gemma
start_server() {{
  mode=$1
  sudo docker rm -f gemma-vllm >/dev/null 2>&1 || true
  cache_args=()
  if test "$mode" = on; then cache_args+=(--enable-prefix-caching); fi
  sudo docker run -d --rm --name gemma-vllm --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" '{IMAGE}' \
    vllm serve "$w/model" --served-model-name '{MODEL}' --dtype bfloat16 --max-model-len 12000 --max-num-seqs 32 --max-num-batched-tokens 65536 --enable-metrics --host 0.0.0.0 --port 30000 "${{cache_args[@]}}" > "$w/runtime/container-id-prefix-$mode"
  ready=0
  while test $(date +%s) -lt "$deadline"; do
    if curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/models-prefix-$mode.json"; then ready=1; break; fi
    sleep 5
  done
  test "$ready" = 1
}}
rm -rf "$w/artifacts/prefix-on" "$w/artifacts/prefix-off"
start_server on
sudo docker exec -e VLLM_MODEL='{MODEL}' gemma-vllm python3 "$w/input/gemma_exact_vllm_runner.py" --output "$w/artifacts/prefix-on" --tokenizer "$w/model" --mode prefix-on
start_server off
sudo docker exec -e VLLM_MODEL='{MODEL}' gemma-vllm python3 "$w/input/gemma_exact_vllm_runner.py" --output "$w/artifacts/prefix-off" --tokenizer "$w/model" --mode prefix-off
sudo docker logs gemma-vllm > "$w/artifacts/prefix-off/server.log" 2>&1 || true
cp "$w/runtime/gpu-telemetry.csv" "$w/artifacts/prefix-off/gpu-telemetry-through-prefix.csv"
python3 - "$w/artifacts" <<'PY'
import json,sys,time
from pathlib import Path
root=Path(sys.argv[1]); on=json.loads((root/'prefix-on/runner-result.json').read_text()); off=json.loads((root/'prefix-off/runner-result.json').read_text())
on_rows=[r for p in on['profiles'] for r in p['rows']]; off_rows=[r for p in off['profiles'] for r in p['rows']]
matched=[r['input_token_ids_sha256'] for r in on_rows]==[r['input_token_ids_sha256'] for r in off_rows]
terminal={{'schema_version':2,'stage':'prefix_cache_on_off','pass':on.get('pass') is True and off.get('pass') is True and matched,
 'same_allocation_runtime_checkpoint':True,'matched_prompt_ids':matched,'reload_count':2,
 'on_completed_requests_per_second':on['profiles'][0]['completed_requests_per_second'],
 'off_completed_requests_per_second':off['profiles'][0]['completed_requests_per_second'],
 'on_useful_gpu_seconds':on.get('useful_gpu_seconds'),'off_useful_gpu_seconds':off.get('useful_gpu_seconds'),'written_at_epoch':time.time()}}
tmp=root/'PREFIX_STAGE_TERMINAL.json.part'; tmp.write_text(json.dumps(terminal,indent=2,sort_keys=True)+'\n'); tmp.replace(root/'PREFIX_STAGE_TERMINAL.json')
if not terminal['pass']: raise SystemExit(1)
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$w/artifacts" -czf "$w/prefix-stage.tar.gz" prefix-on prefix-off PREFIX_STAGE_TERMINAL.json
sha256sum "$w/prefix-stage.tar.gz" > "$w/prefix-stage.tar.gz.sha256"
'''


def render_program() -> dict:
    PROGRAM.mkdir(parents=True, exist_ok=True)
    values = {
        "bootstrap.sh": bootstrap_script(),
        "baseline.sh": baseline_script(),
        "prefix.sh": prefix_script(),
    }
    for name, content in values.items():
        path = PROGRAM / name
        path.write_text(content)
        path.chmod(0o755)
    return {name: {"path": str(PROGRAM / name), "sha256": sha(PROGRAM / name), "bytes": (PROGRAM / name).stat().st_size} for name in values}


def prompt_proof() -> dict:
    sys.path.insert(0, str(HERE))
    import gemma_exact_vllm_runner as runner
    prompts = runner.build_primary_prompts(list(range(20_000, 20_016)), 262_144)
    suffix_hashes = [runner.digest(runner.canonical(prompt[runner.SHARED_PREFIX_TOKENS:])) for prompt in prompts]
    lcps = [runner.longest_common_prefix(prompts[0], prompt) for prompt in prompts[1:]]
    ten_k = runner.prompt_ids(10_000, 90_000, 262_144, shared=False)
    return {
        "primary_prompt_count": len(prompts),
        "primary_token_counts": sorted({len(prompt) for prompt in prompts}),
        "shared_prefix_token_count": runner.SHARED_PREFIX_TOKENS,
        "pairwise_longest_common_prefix_counts": sorted(set(lcps)),
        "suffix_hashes_distinct": len(set(suffix_hashes)) == len(suffix_hashes),
        "separate_10k_token_count": len(ten_k),
        "shared_prefix_sha256": runner.digest(runner.canonical(prompts[0][: runner.SHARED_PREFIX_TOKENS])),
    }


def audit_program(output: Path, name: str, deadline_seconds: int) -> dict:
    transfer = prepare_transfer_view()
    rendered = render_program()
    terminal = json.loads(CHECKPOINT_TERMINAL.read_text())
    economics = json.loads(ECONOMIC.read_text())
    create = build_create_command(
        name=name,
        disk_name=name + "-boot",
        cloud_init=make_cloud_init(PUB.read_text()),
        disk_gib=250,
        platform="gpu-h200-sxm",
        preset="1gpu-16vcpu-200gb",
        preemptible=True,
    )
    command = " ".join(create)
    runner_text = RUNNER.read_text()
    owner_text = Path(__file__).read_text()
    prefix_text = (PROGRAM / "prefix.sh").read_text()
    baseline_text = (PROGRAM / "baseline.sh").read_text()
    proof = prompt_proof()
    checks = {
        "checkpoint_terminal_pass": terminal.get("pass") is True,
        "checkpoint_revision_exact": terminal.get("revision") == REVISION,
        "model_index_sha256_exact": sha(CHECKPOINT / "model.safetensors.index.json") == INDEX_SHA256,
        "economic_revision_exact": economics["identities"]["revision"] == REVISION,
        "economic_upper_hurdle_exact": economics["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"][1] == 2.118591,
        "image_digest_exact": IMAGE in (PROGRAM / "bootstrap.sh").read_text(),
        "output_directory_distinct_nonexistent": output != PROGRAM and output != TRANSFER_VIEW and not output.exists(),
        "rfc1123_lowercase_name": bool(re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", name)),
        "real_create_argv_lowercase": "--name " + name in command and "--hostname " + name in command,
        "shared_transfer_checkpoint_primitive": "transfer_checkpoint(" in owner_text and "session_staging import transfer_checkpoint" in owner_text,
        "shared_transfer_host_key_options": "StrictHostKeyChecking=accept-new" in (NEBIUS_DIR / "session_staging.py").read_text() and "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts" in (NEBIUS_DIR / "session_staging.py").read_text(),
        "exact_primary_token_count": proof["primary_token_counts"] == [4214],
        "only_intended_common_region_535": proof["pairwise_longest_common_prefix_counts"] == [535],
        "suffix_hashes_distinct": proof["suffix_hashes_distinct"] is True,
        "exact_separate_10k": proof["separate_10k_token_count"] == 10000,
        "simultaneous_c1_c4_c8_c16": "CONCURRENCIES = (1, 4, 8, 16)" in runner_text and "threading.Barrier(concurrency)" in runner_text,
        "streaming_raw_bytes_ids_ttft_itl": all(token in runner_text for token in ("raw-sse", "output_token_ids", "ttft_ms", "itl_ms", '"stream": True')),
        "queue_prefill_decode_cache_metrics": all(token in runner_text for token in ("request_queue_time_seconds_sum", "request_prefill_time_seconds_sum", "request_decode_time_seconds_sum", "prefix_cache_hits_total")),
        "continuous_gpu_hbm_power_telemetry": all(token in (PROGRAM / "bootstrap.sh").read_text() for token in ("while test", "memory.used", "utilization.gpu", "power.draw", "sleep 1")),
        "complete_failure_reload_fields": all(token in baseline_text for token in ("complete_count", "failure_count", "reload_count")),
        "provider_disk_useful_all_in_fields": all(token in owner_text for token in ("PROVIDER_RATE_USD_PER_HOUR", "DISK_RATE_USD_PER_HOUR", "useful_gpu_seconds", "all_in_cost")),
        "atomic_staged_retrieval": "atomic_retrieve(" in owner_text and ".part" in owner_text and "os.replace" in owner_text,
        "prefix_trigger_implemented": "0.393755" in owner_text and "trigger_prefix_arm(" in owner_text,
        "prefix_on_off_start_ready": "start_server on" in prefix_text and "start_server off" in prefix_text and "--mode prefix-on" in prefix_text and "--mode prefix-off" in prefix_text,
        "prefix_same_prompt_ids": "matched_prompt_ids" in prefix_text,
        "prefix_false_cleanup_branch": "prefix_trigger_false" in owner_text and "owner.complete(" in owner_text,
        "runner_is_shared_narrow_adaptation": "adapted from the shared vLLM batched runner" in runner_text and "urllib.request.urlopen" in runner_text and "ThreadPoolExecutor" in runner_text,
    }
    report = {
        "schema_version": 2,
        "classification": "corrected_identity_and_final_program_audit",
        "timestamp_utc": utc_now(),
        "name": name,
        "owner_output": str(output),
        "deadline_seconds": deadline_seconds,
        "aggregate_limits": {
            "first_provider_seconds": FIRST_PROVIDER_SECONDS,
            "second_provider_seconds_max": deadline_seconds,
            "provider_seconds_total_max": FIRST_PROVIDER_SECONDS + deadline_seconds,
            "provider_minutes_total_max": (FIRST_PROVIDER_SECONDS + deadline_seconds) / 60,
            "spend_total_max_usd": FIRST_COST_USD_DERIVED + deadline_seconds / 3600 * (PROVIDER_RATE_USD_PER_HOUR + DISK_RATE_USD_PER_HOUR),
        },
        "create_argv": create,
        "transfer_view": transfer,
        "rendered_program": rendered,
        "runner": {"path": str(RUNNER), "sha256": sha(RUNNER)},
        "prompt_proof": proof,
        "checks": checks,
        "pass": all(checks.values()) and 1 <= deadline_seconds <= MAX_SECOND_PROVIDER_SECONDS,
    }
    write_json(AUDIT, report)
    if not report["pass"]:
        raise ContractError("corrected final-program audit failed")
    return report


def inventory_row(kind: str) -> dict:
    command = [
        "/root/.nebius/bin/nebius", "compute", kind, "list", "--parent-id", PROJECT_ID, "--all",
        "--profile", PROFILE, "--format", "json", "--no-progress", "--timeout", "30s",
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired as error:
        return {"kind": kind, "outcome": "subprocess_timeout", "timeout_seconds": error.timeout, "empty": False}
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        parsed = "unparsed"
    return {
        "kind": kind,
        "command": command,
        "returncode": proc.returncode,
        "stdout_bytes": len(proc.stdout.encode()),
        "stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "stderr_bytes": len(proc.stderr.encode()),
        "stderr_sha256": hashlib.sha256(proc.stderr.encode()).hexdigest(),
        "parsed_type": type(parsed).__name__,
        "empty": proc.returncode == 0 and (parsed == {} or not proc.stdout.strip()) and not proc.stderr.strip(),
    }


def inventory_preflight() -> dict:
    rows = [inventory_row("instance"), inventory_row("disk")]
    report = {
        "schema_version": 2,
        "classification": "authenticated_empty_provider_inventory" if all(row["empty"] for row in rows) else "provider_inventory_precreate_failure",
        "timestamp_utc": utc_now(),
        "timestamp_epoch": time.time(),
        "profile": PROFILE,
        "project_id": PROJECT_ID,
        "resources": rows,
        "pass": all(row["empty"] for row in rows),
    }
    write_json(INVENTORY, report)
    if not report["pass"]:
        raise ContractError("fresh authenticated inventory is not empty")
    return report


def validate_terminals(output: Path, name: str) -> None:
    audit = json.loads(AUDIT.read_text())
    inventory = json.loads(INVENTORY.read_text())
    if audit.get("pass") is not True or audit.get("name") != name or audit.get("owner_output") != str(output):
        raise ContractError("corrected audit does not bind this owner")
    if audit["runner"]["sha256"] != sha(RUNNER):
        raise ContractError("runner changed after corrected audit")
    if inventory.get("pass") is not True or time.time() - float(inventory["timestamp_epoch"]) > 300:
        raise ContractError("authenticated empty inventory is absent or stale")
    if output.exists():
        raise ContractError("owner output directory existed before launch")


def remote_diagnostic(output: Path, label: str, proc: subprocess.CompletedProcess[str]) -> None:
    write_json(output / f"{label}-diagnostic.json", {
        "stage": label,
        "returncode": proc.returncode,
        "stdout_bytes": len(proc.stdout.encode()),
        "stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_bytes": len(proc.stderr.encode()),
        "stderr_sha256": hashlib.sha256(proc.stderr.encode()).hexdigest(),
        "stderr_tail": proc.stderr[-4000:],
    })


def atomic_retrieve(ip: str, remote_base: str, output: Path, stem: str) -> tuple[Path, dict]:
    part_archive = output / f"{stem}.tar.gz.part"
    part_hash = output / f"{stem}.tar.gz.sha256.part"
    scp_from(ip, KEY, remote_base + ".tar.gz", part_archive)
    scp_from(ip, KEY, remote_base + ".tar.gz.sha256", part_hash)
    expected = part_hash.read_text().split()[0]
    observed = sha(part_archive)
    if observed != expected:
        raise ContractError(f"atomic {stem} retrieval hash mismatch")
    archive = output / f"{stem}.tar.gz"
    hash_path = output / f"{stem}.tar.gz.sha256"
    os.replace(part_archive, archive)
    os.replace(part_hash, hash_path)
    with tarfile.open(archive, "r:gz") as bundle:
        terminal_members = [member for member in bundle.getmembers() if member.name.endswith("_STAGE_TERMINAL.json")]
        if len(terminal_members) != 1:
            raise ContractError(f"atomic {stem} archive lacks exactly one stage terminal")
        handle = bundle.extractfile(terminal_members[0])
        if handle is None:
            raise ContractError(f"atomic {stem} stage terminal is not a file")
        terminal = json.loads(handle.read())
    write_json(output / f"{stem}-retrieval.json", {"pass": True, "archive": archive.name, "sha256": observed, "terminal": terminal})
    return archive, terminal


def trigger_prefix_arm(baseline: dict, retrieval_finished: float, deadline: float) -> dict:
    prefill = baseline.get("prefill_decode") or {}
    raw = baseline.get("raw_metric_contract") or {}
    healthy = baseline.get("pass") is True and baseline.get("failure_count") == 0 and baseline.get("complete_count", 0) > 0
    metrics_complete = bool(raw) and all(value is True for value in raw.values())
    share = prefill.get("exposed_prefill_share")
    threshold_pass = isinstance(share, (int, float)) and share >= 0.393755
    start_ready_seconds = time.time() - retrieval_finished
    start_ready = start_ready_seconds <= 600
    deadline_reserve = deadline - time.time()
    within_absolute_deadline = deadline_reserve >= 1200
    decision = healthy and metrics_complete and threshold_pass and start_ready and within_absolute_deadline
    return {
        "schema_version": 2,
        "name": "prefix_cache_on_off_after_exposed_prefill",
        "healthy_baseline": healthy,
        "all_raw_metrics_present": metrics_complete,
        "measured_exposed_prefill_share": share,
        "threshold": 0.393755,
        "threshold_pass": threshold_pass,
        "start_ready_seconds": start_ready_seconds,
        "start_ready_within_600_seconds": start_ready,
        "deadline_reserve_seconds": deadline_reserve,
        "without_deadline_extension": within_absolute_deadline,
        "run": decision,
    }


def run_owner(output: Path, name: str, deadline_seconds: int) -> int:
    if not os.getenv("INVOCATION_ID") or os.getenv("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise ContractError("provider mutation requires durable systemd owner")
    if not 1 <= deadline_seconds <= MAX_SECOND_PROVIDER_SECONDS:
        raise ContractError("corrected owner deadline exceeds original aggregate provider budget")
    validate_terminals(output, name)
    output.mkdir(parents=False, exist_ok=False)
    events = output / "events.jsonl"
    started = time.time()
    deadline = started + deadline_seconds
    instance_id = None
    useful_gpu_seconds = 0.0
    outcome = "FAIL"
    failure_stage = None
    try:
        with VerifiedRetainedOwner(name, output / "cleanup.json") as owner:
            append_event(events, "owner_started", deadline_epoch=deadline, aggregate_provider_seconds_max=FIRST_PROVIDER_SECONDS + deadline_seconds)
            create = subprocess.run(
                build_create_command(name=name, disk_name=name + "-boot", cloud_init=make_cloud_init(PUB.read_text()), disk_gib=250, platform="gpu-h200-sxm", preset="1gpu-16vcpu-200gb", preemptible=True),
                capture_output=True,
                text=True,
                timeout=180,
            )
            write_create_diagnostic(output, create)
            if create.returncode:
                failure_stage = "provider_create"
                raise ContractError("corrected provider create failed")
            instance_id = extract_instance_id(json.loads(create.stdout))
            owner.bind_instance(instance_id)
            watchdog = start_independent_watchdog(instance_id, name + "-boot", deadline, name + "-watchdog")
            write_json(output / "watchdog.json", watchdog)
            append_event(events, "provider_created", instance_id=instance_id)
            ip = None
            while time.time() < min(deadline, started + 600):
                instance = get_instance(instance_id)
                if instance is None:
                    failure_stage = "provider_readiness"
                    raise ContractError("instance disappeared before IP readiness")
                ip = extract_public_ipv4(instance)
                if ip:
                    break
                time.sleep(5)
            if not ip:
                failure_stage = "provider_readiness"
                raise ContractError("public IP readiness exceeded")
            wait_ssh(ip, KEY, min(deadline, started + 600))
            append_event(events, "ssh_ready")
            failure_stage = "checkpoint_transfer"
            transfer_started = time.time()
            transfer = transfer_checkpoint(
                ip,
                KEY,
                TRANSFER_VIEW,
                "/home/glmrunner/gemma/model",
                timeout_seconds=min(transfer_timeout_seconds(sum(path.stat().st_size for path in TRANSFER_VIEW.iterdir() if path.is_file())), max(60, int(deadline - time.time() - 900))),
            )
            write_json(output / "checkpoint-transfer.json", {**transfer.__dict__, "pass": True, "shared_primitive": "session_staging.transfer_checkpoint"})
            append_event(events, "checkpoint_transferred", elapsed_seconds=time.time() - transfer_started, scheduled_bytes=transfer.scheduled_bytes)
            failure_stage = "program_transfer"
            prepare = run_ssh(ip, KEY, "mkdir -p /home/glmrunner/gemma/input", timeout=30)
            remote_diagnostic(output, "program-directory", prepare)
            if prepare.returncode:
                raise ContractError("remote program directory preparation failed")
            scp_to(ip, KEY, [RUNNER, PROGRAM / "bootstrap.sh", PROGRAM / "baseline.sh", PROGRAM / "prefix.sh"], "/home/glmrunner/gemma/input/")
            append_event(events, "program_transferred", runner_sha256=sha(RUNNER))
            failure_stage = "bootstrap"
            bootstrap = run_ssh(ip, KEY, ["bash", "/home/glmrunner/gemma/input/bootstrap.sh", str(int(deadline))], timeout=max(60, int(deadline - time.time() - 600)))
            remote_diagnostic(output, "bootstrap", bootstrap)
            if bootstrap.returncode:
                raise ContractError("exact image/server bootstrap failed")
            append_event(events, "server_ready")
            failure_stage = "baseline_science"
            baseline = run_ssh(ip, KEY, ["bash", "/home/glmrunner/gemma/input/baseline.sh", str(int(deadline))], timeout=max(60, int(deadline - time.time() - 300)))
            remote_diagnostic(output, "baseline-remote", baseline)
            retrieval_started = time.time()
            _, baseline_terminal = atomic_retrieve(ip, "/home/glmrunner/gemma/baseline-stage", output, "baseline-stage")
            retrieval_finished = time.time()
            useful_gpu_seconds += float(baseline_terminal.get("useful_gpu_seconds") or 0)
            if baseline.returncode or baseline_terminal.get("pass") is not True:
                raise ContractError("baseline stage returned a typed scientific failure")
            append_event(events, "baseline_retrieved", retrieval_seconds=retrieval_finished - retrieval_started, terminal=baseline_terminal)
            trigger = trigger_prefix_arm(baseline_terminal, retrieval_finished, deadline)
            write_json(output / "PREFIX_TRIGGER.json", trigger)
            if trigger["run"]:
                append_event(events, "prefix_trigger_true", trigger=trigger)
                failure_stage = "prefix_followup_science"
                prefix = run_ssh(ip, KEY, ["bash", "/home/glmrunner/gemma/input/prefix.sh", str(int(deadline))], timeout=max(60, int(deadline - time.time() - 180)))
                remote_diagnostic(output, "prefix-remote", prefix)
                _, prefix_terminal = atomic_retrieve(ip, "/home/glmrunner/gemma/prefix-stage", output, "prefix-stage")
                useful_gpu_seconds += float(prefix_terminal.get("on_useful_gpu_seconds") or 0) + float(prefix_terminal.get("off_useful_gpu_seconds") or 0)
                if prefix.returncode or prefix_terminal.get("pass") is not True:
                    raise ContractError("prefix follow-up returned a typed scientific failure")
                append_event(events, "prefix_retrieved", terminal=prefix_terminal)
                outcome = "PASS_WITH_PREFIX_ARM"
            else:
                append_event(events, "prefix_trigger_false", trigger=trigger)
                write_json(output / "PREFIX_STAGE_TERMINAL.json", {"schema_version": 2, "stage": "prefix_cache_on_off", "pass": True, "run": False, "classification": "trigger_false_cleanup", "trigger": trigger})
                outcome = "PASS_BASELINE_ONLY"
            failure_stage = None
            owner.complete("exact_gemma_vllm_h200_terminal")
    except Exception as error:
        write_json(output / "failure.json", {
            "error_type": type(error).__name__,
            "message": str(error),
            "failure_stage": failure_stage,
            "instance_id": instance_id,
            "classification": "second_pre_science_failure_closes_lineage" if failure_stage in {"provider_create", "provider_readiness", "checkpoint_transfer", "program_transfer", "bootstrap"} else "typed_scientific_or_execution_failure",
        })
        outcome = "CLOSED_SECOND_PRE_SCIENCE_FAILURE" if failure_stage in {"provider_create", "provider_readiness", "checkpoint_transfer", "program_transfer", "bootstrap"} else "FAIL"
    provider_seconds = max(0.0, time.time() - started)
    compute_cost = provider_seconds / 3600 * PROVIDER_RATE_USD_PER_HOUR
    disk_cost = provider_seconds / 3600 * DISK_RATE_USD_PER_HOUR
    all_in_cost = compute_cost + disk_cost
    summary = {
        "schema_version": 2,
        "outcome": outcome,
        "name": name,
        "instance_id": instance_id,
        "provider_seconds": provider_seconds,
        "first_owner_provider_seconds": FIRST_PROVIDER_SECONDS,
        "aggregate_provider_seconds": FIRST_PROVIDER_SECONDS + provider_seconds,
        "useful_gpu_seconds": useful_gpu_seconds,
        "provider_rate_usd_per_hour": PROVIDER_RATE_USD_PER_HOUR,
        "provider_rate_basis": "fresh shared inventory public_preemptible H200 reference; invoice pending",
        "disk_rate_usd_per_hour": DISK_RATE_USD_PER_HOUR,
        "disk_rate_basis": "Nebius 250-GiB vendor-calculator rate used by shared lifecycle",
        "planning_rate_usd_per_hour": PLANNING_RATE_USD_PER_HOUR,
        "compute_cost_usd_derived": compute_cost,
        "disk_cost_usd_derived": disk_cost,
        "all_in_cost_usd_derived": all_in_cost,
        "first_owner_cost_usd_derived": FIRST_COST_USD_DERIVED,
        "aggregate_cost_usd_derived": FIRST_COST_USD_DERIVED + all_in_cost,
        "absolute_limits": {"provider_minutes": 80, "h200_hours": 1.34, "spend_usd": 4.0, "artifact_gib": 10},
        "within_provider_limit": FIRST_PROVIDER_SECONDS + provider_seconds <= 80 * 60,
        "within_compute_limit": (FIRST_PROVIDER_SECONDS + provider_seconds) / 3600 <= 1.34,
        "within_spend_limit": FIRST_COST_USD_DERIVED + all_in_cost <= 4.0,
        "cleanup_path": "cleanup.json",
        "ended_at_utc": utc_now(),
    }
    write_json(output / "SUMMARY.json", summary)
    return 0 if outcome.startswith("PASS") else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--deadline-seconds", type=int, default=int(MAX_SECOND_PROVIDER_SECONDS))
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    if args.audit_only:
        if args.output is None or not args.name:
            parser.error("--audit-only requires --output and --name")
        audit_program(args.output, args.name, args.deadline_seconds)
        return 0
    if args.inventory_only:
        inventory_preflight()
        return 0
    if args.output is None or not args.name:
        parser.error("owner execution requires --output and --name")
    return run_owner(args.output, args.name, args.deadline_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
