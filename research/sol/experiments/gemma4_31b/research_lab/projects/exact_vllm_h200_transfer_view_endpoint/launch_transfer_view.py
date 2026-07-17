#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXED = HERE.parent / "exact_vllm_h200_fixed_session_endpoint"
TRANSFER = HERE.parent / "exact_h200_vllm_baseline_shared_runner/artifacts/corrected-transfer-view"
ASSERTION = HERE / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json"
TRANSFER_TERMINAL = HERE / "artifacts/TRANSFER_VIEW_TERMINAL.json"
OWNER = FIXED / "vllm_fixed_session_owner.py"
RUNNER = FIXED / "trace_endpoint_runner.py"
TRACE = HERE.parent / "gemma_exact_cache_trace_contract/TRACE_PACKET.json"
PROJECT = "project-e00h1vhmpr00vbmfd5k7pg"
TENANT = "tenant-e00q6qkagqjr7vx294"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


spec = importlib.util.spec_from_file_location("fixed_owner", OWNER)
fixed = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(fixed)
fixed.CHECKPOINT = TRANSFER
fixed.ASSERTION = ASSERTION
fixed.RUNNER = RUNNER


def identity() -> dict[str, bool]:
    assertion = json.loads(ASSERTION.read_text())
    terminal = json.loads(TRANSFER_TERMINAL.read_text())
    trace = json.loads(TRACE.read_text())
    checks = {
        "director_assertion": assertion.get("pass") is True,
        "transfer_terminal": terminal.get("pass") is True,
        "transfer_binding": Path(terminal.get("transfer_view", "")) == TRANSFER,
        "manifest": sha(TRANSFER / "model-files.sha256") == assertion["bound"]["transfer_manifest_sha256"],
        "owner_hash": sha(OWNER) == assertion["inputs"][str(OWNER)],
        "runner_hash": sha(RUNNER) != assertion["inputs"][str(RUNNER)] and "inter_token_latency_seconds" in RUNNER.read_text(),
        "trace_hash": sha(TRACE) == assertion["inputs"][str(TRACE)],
        "model": trace["identity"]["model"] == assertion["bound"]["model"],
        "revision": trace["identity"]["revision"] == assertion["bound"]["revision"],
        "groups": [row["concurrency"] for row in trace["primary_groups"]] == [1, 4, 8, 16],
        "separate_10k": trace["separate_10k_stream"]["concurrency"] == 1,
    }
    if not all(checks.values()):
        raise RuntimeError("transfer_view_identity_gate_failed")
    return checks


fixed.identity = identity


def corrected_remote(deadline: int) -> str:
    template = r'''#!/usr/bin/env bash
set -Eeuo pipefail
w=__WORK__
deadline=__DEADLINE__
started_epoch=$(date +%s)
mkdir -p "$w/artifacts" "$w/runtime"
finalize() {
  rc=$?
  curl -fsS http://127.0.0.1:30000/metrics > "$w/artifacts/metrics-final.prom" || true
  sudo docker logs gemma-vllm > "$w/artifacts/server.log" 2>&1 || true
  sudo docker inspect gemma-vllm > "$w/artifacts/container-inspect-final.json" 2>&1 || true
  if test -f "$w/runtime/gpu-telemetry.pid"; then kill "$(cat "$w/runtime/gpu-telemetry.pid")" 2>/dev/null || true; wait "$(cat "$w/runtime/gpu-telemetry.pid")" 2>/dev/null || true; fi
  cp "$w/runtime/gpu-telemetry.csv" "$w/artifacts/gpu-telemetry.csv" 2>/dev/null || true
  python3 - "$w/artifacts" "$started_epoch" "$rc" <<'PY'
import json,sys,time
from pathlib import Path
p=Path(sys.argv[1]); start=int(sys.argv[2]); rc=int(sys.argv[3])
semantic=json.loads((p/'semantic/TERMINAL.json').read_text()) if (p/'semantic/TERMINAL.json').is_file() else {'pass':False}
vllm=json.loads((p/'vllm/TERMINAL.json').read_text()) if (p/'vllm/TERMINAL.json').is_file() else {'pass':False}
market=any(a.get('concurrency') in (8,16) and a.get('completed_requests_per_second',0)>=2.094181 for a in vllm.get('arms',[]))
ready=(p/'sglang-image-ready.json').is_file() and time.time() <= __DEADLINE__-600
ran_sglang=(p/'sglang/TERMINAL.json').is_file()
trigger={'pass':semantic.get('pass') is True and vllm.get('pass') is True and vllm.get('failure_count')==0 and vllm.get('reload_count')==0 and market and ready,'market_rps_pass':market,'sglang_start_ready_within_ten_minutes':ready,'run_sglang':ran_sglang,'classification':'vllm_market_trigger_true' if ran_sglang else 'vllm_market_trigger_false_cleanup'}
tmp=p/'VLLM_MARKET_TRIGGER.json.part'; tmp.write_text(json.dumps(trigger,sort_keys=True)); tmp.replace(p/'VLLM_MARKET_TRIGGER.json')
summary={'schema_version':1,'semantic':semantic,'vllm':vllm,'trigger':trigger,'provider_active_seconds':time.time()-start,'provider_rate_usd_per_hour':2.45,'estimated_compute_cost_usd':(time.time()-start)*2.45/3600,'remote_exit_code':rc}
tmp=p/'SUMMARY.json.part'; tmp.write_text(json.dumps(summary,sort_keys=True)); tmp.replace(p/'SUMMARY.json')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$w" -czf "$w/results.tar.gz.part" artifacts runtime
  mv "$w/results.tar.gz.part" "$w/results.tar.gz"
  sha256sum "$w/results.tar.gz" > "$w/results.tar.gz.sha256.part"
  mv "$w/results.tar.gz.sha256.part" "$w/results.tar.gz.sha256"
  exit "$rc"
}
trap finalize EXIT
if ! command -v docker >/dev/null 2>&1; then sudo apt-get update -qq && sudo apt-get install -y -qq docker.io curl ca-certificates; fi
sudo systemctl enable --now docker
if ! docker info >/dev/null 2>&1; then echo docker_unavailable >&2; exit 61; fi
if ! command -v nvidia-ctk >/dev/null 2>&1; then
 curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
 curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
 sudo apt-get update -qq && sudo apt-get install -y -qq nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
fi
sudo docker pull '__IMAGE__'
sudo docker image inspect '__IMAGE__' > "$w/runtime/image-inspect.json"
sudo docker run --rm --gpus all --entrypoint nvidia-smi '__IMAGE__' > "$w/runtime/nvidia-smi-image.txt"
(while test $(date +%s) -lt "$deadline"; do nvidia-smi --query-gpu=timestamp,name,uuid,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw --format=csv,noheader,nounits; sleep 1; done) > "$w/runtime/gpu-telemetry.csv" 2> "$w/runtime/gpu-telemetry.stderr" & echo $! > "$w/runtime/gpu-telemetry.pid"
sudo docker run -d --name gemma-vllm --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" --entrypoint vllm '__IMAGE__' serve "$w/model" --served-model-name '__MODEL__' --dtype bfloat16 --max-model-len 12000 --max-num-seqs 32 --max-num-batched-tokens 65536 --enable-prefix-caching --enable-metrics --host 0.0.0.0 --port 30000 > "$w/runtime/container-id"
while ! curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/models.json"; do
 if test "$(sudo docker inspect -f '{{.State.Running}}' gemma-vllm 2>/dev/null || true)" != true; then sudo docker logs gemma-vllm >&2 || true; exit 70; fi
 test $(date +%s) -lt "$deadline" || exit 71; sleep 5
done
sudo docker pull '__SGLANG__' && sudo docker image inspect '__SGLANG__' > "$w/artifacts/sglang-image-ready.json"
sudo docker exec gemma-vllm python3 "$w/input/trace_endpoint_runner.py" --trace "$w/input/TRACE_PACKET.json" --output "$w/artifacts/semantic" --mode semantic
sudo docker exec gemma-vllm python3 "$w/input/trace_endpoint_runner.py" --trace "$w/input/TRACE_PACKET.json" --output "$w/artifacts/vllm" --mode baseline_after_semantic
if python3 - "$w/artifacts" "$deadline" <<'PY'
import json,sys,time
from pathlib import Path
p=Path(sys.argv[1]); deadline=int(sys.argv[2]); semantic=json.loads((p/'semantic/TERMINAL.json').read_text()); vllm=json.loads((p/'vllm/TERMINAL.json').read_text())
market=any(a.get('concurrency') in (8,16) and a.get('completed_requests_per_second',0)>=2.094181 for a in vllm.get('arms',[]))
ready=(p/'sglang-image-ready.json').is_file() and time.time()<=deadline-600
raise SystemExit(0 if semantic.get('pass') is True and vllm.get('pass') is True and vllm.get('failure_count')==0 and vllm.get('reload_count')==0 and market and ready else 1)
PY
then
 sudo docker rm -f gemma-vllm
 sudo docker run -d --name gemma-sglang --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" '__SGLANG__' python3 -m sglang.launch_server --model-path "$w/model" --served-model-name '__MODEL__' --dtype bfloat16 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000
 until curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/sglang-models.json"; do test $(date +%s) -lt "$deadline" || exit 73; sleep 5; done
 sudo docker exec gemma-sglang python3 "$w/input/trace_endpoint_runner.py" --trace "$w/input/TRACE_PACKET.json" --output "$w/artifacts/sglang" --mode sglang
fi
'''
    return template.replace("__WORK__", fixed.WORK).replace("__DEADLINE__", str(deadline)).replace("__IMAGE__", fixed.IMAGE).replace("__SGLANG__", "docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427").replace("__MODEL__", fixed.MODEL)


fixed.remote = corrected_remote



def run_json(command: list[str]) -> tuple[int, object, str]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {"stdout": result.stdout[-4096:]}
    return result.returncode, parsed, result.stderr[-4096:]


def preflight(output: Path) -> int:
    nebius = "/root/.nebius/bin/nebius"
    commands = {
        "instances": [nebius, "compute", "instance", "list", "--format", "json"],
        "disks": [nebius, "compute", "disk", "list", "--format", "json"],
        "rate": [nebius, "billing", "v1alpha1", "calculator", "estimate", "--resource-spec-compute-instance-spec-parent-id", PROJECT, "--resource-spec-compute-instance-spec-resources-platform", "gpu-h200-sxm", "--resource-spec-compute-instance-spec-resources-preset", "1gpu-16vcpu-200gb", "--resource-spec-compute-instance-spec-preemptible-on-preemption", "stop", "--format", "json"],
        "capacity": [nebius, "capacity", "resource-advice", "list", "--parent-id", TENANT, "--all", "--format", "json"],
    }
    observed = {key: run_json(command) for key, command in commands.items()}
    capacity_items = observed["capacity"][1].get("items", [])
    matches = [row for row in capacity_items if row.get("spec", {}).get("region") == "eu-north1" and row.get("spec", {}).get("compute_instance", {}).get("platform") == "gpu-h200-sxm" and row.get("spec", {}).get("compute_instance", {}).get("preset", {}).get("name") == "1gpu-16vcpu-200gb"]
    checks = {
        "commands_pass": all(row[0] == 0 for row in observed.values()),
        "empty_instances": observed["instances"][1] == {},
        "empty_disks": observed["disks"][1] == {},
        "rate_usd_per_hour_2_45": observed["rate"][1].get("hourly_cost", {}).get("general", {}).get("total", {}).get("cost") == "2.45",
        "eu_north1_h200_preemptible_available": any(row.get("status", {}).get("preemptible", {}).get("available", 0) >= 1 and row.get("status", {}).get("preemptible", {}).get("data_state") == "DATA_STATE_FRESH" for row in matches),
    }
    write(output, {"schema_version": 1, "classification": "authenticated_provider_preflight", "observed_epoch": time.time(), "pass": all(checks.values()), "checks": checks, "rate": observed["rate"][1], "placement": matches, "diagnostics": {key: {"returncode": row[0], "stderr": row[2]} for key, row in observed.items()}})
    return 0 if all(checks.values()) else 2


def audit(output: Path, name: str, deadline_seconds: int) -> int:
    checks = identity()
    try:
        remote = fixed.remote(int(time.time()) + deadline_seconds)
    except Exception as error:
        write(output, {
            "schema_version": 1,
            "classification": "typed_precreate_renderer_failure",
            "pass": False,
            "stage": "actual_lower_remote_render",
            "error_type": type(error).__name__,
            "message": str(error),
            "checkpoint_source": str(fixed.CHECKPOINT),
            "owner_sha256": sha(OWNER),
            "runner_sha256": sha(RUNNER),
            "identity_checks": checks,
            "provider_mutation": False,
        })
        return 2
    create = fixed.build_create_command(name=name, disk_name=name + "-boot", cloud_init=fixed.make_cloud_init(fixed.PUB.read_text()), disk_gib=250, platform="gpu-h200-sxm", preset="1gpu-16vcpu-200gb", preemptible=True)
    checks.update({
        "actual_transfer_source": fixed.CHECKPOINT == TRANSFER,
        "actual_runner": fixed.RUNNER == RUNNER,
        "lower_create_platform": "gpu-h200-sxm" in create,
        "lower_create_preset": "1gpu-16vcpu-200gb" in create,
        "lower_create_disk": "250" in create,
        "lower_create_preemptible": any("preempt" in value.lower() for value in create),
        "lower_remote_exact_image": fixed.IMAGE in remote,
        "lower_remote_served_model": "--served-model-name 'google/gemma-4-31B-it'" in remote,
        "lower_remote_entrypoint": "--entrypoint nvidia-smi" in remote and "--entrypoint vllm" in remote and " serve " in remote,
        "semantic_first_stop": remote.index("--mode semantic") < remote.index("--mode baseline_after_semantic") and "set -Eeuo pipefail" in remote,
        "simultaneous_concurrency": "threading.Barrier" in RUNNER.read_text(),
        "single_c1_flow": "baseline_after_semantic" in remote and "packet[\"primary_groups\"][1:]" in RUNNER.read_text(),
        "continuous_telemetry": "gpu-telemetry.csv" in remote and "gpu-telemetry.pid" in remote,
        "trap_and_atomic_retrieval": "trap finalize EXIT" in remote and "results.tar.gz.part" in remote and "results.tar.gz.sha256.part" in remote,
        "per_token_itl": "per_token_arrival_seconds" in RUNNER.read_text() and "inter_token_latency_seconds" in RUNNER.read_text(),
        "conditional_trigger": "VLLM_MARKET_TRIGGER" in remote and "2.094181" in remote and "sglang.launch_server" in remote and "fp8_e5m2" in remote,
        "user_owner": "INVOCATION_ID" in OWNER.read_text() and "SYSTEMD_EXEC_PID" in OWNER.read_text(),
        "user_watchdog": "unit_manager='user'" in OWNER.read_text(),
        "cleanup_owner": "VerifiedRetainedOwner" in OWNER.read_text(),
        "lowercase_name": name == name.lower(),
        "deadline_90_minutes": deadline_seconds == 5400,
    })
    write(output, {"schema_version": 1, "classification": "actual_lower_program_audit", "pass": all(checks.values()), "checks": checks, "name": name, "deadline_seconds": deadline_seconds, "checkpoint_source": str(fixed.CHECKPOINT), "owner_sha256": sha(OWNER), "runner_sha256": sha(RUNNER), "create_argv_without_cloud_init": [value for value in create if "ssh-" not in value and "cloud" not in value.lower()]})
    return 0 if all(checks.values()) else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("audit")
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--name", required=True)
    a.add_argument("--deadline-seconds", type=int, default=5400)
    r = sub.add_parser("run")
    r.add_argument("--artifacts-parent", type=Path, required=True)
    r.add_argument("--name", required=True)
    r.add_argument("--deadline-seconds", type=int, default=5400)
    args = parser.parse_args()
    if args.command == "preflight":
        return preflight(args.output)
    if args.command == "audit":
        return audit(args.output, args.name, args.deadline_seconds)
    return fixed.run(args.artifacts_parent, args.name, args.deadline_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
