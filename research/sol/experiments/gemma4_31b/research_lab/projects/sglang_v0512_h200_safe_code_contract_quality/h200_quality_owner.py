#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
from placement_control import extract_public_ipv4, get_instance, wait_ssh
from stock_control import run_ssh, scp_from, scp_to

KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
IMAGE = "docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a"
MODEL = "google/gemma-4-31B-it"
CHECKPOINT = (PROJECT.parent / "sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint").resolve()
REFERENCE = PROJECT.parent / "sglang_v0512_h200_stock_quality_validation/reference_sentinel.py"
SCORER_DIR = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/quality")
REMOTE = "/home/glmrunner/gemma-safe-code"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def put(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def event(path: Path, phase: str, **fields: object) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps({"timestamp": now(), "phase": phase, **fields}, sort_keys=True) + "\n")


def invoke(ip: str, output: Path, events: Path, label: str, command: str, timeout: int) -> None:
    event(events, label, state="start")
    result = run_ssh(ip, KEY, command, timeout=timeout)
    (output / f"{label}.stdout.log").write_text(result.stdout)
    (output / f"{label}.stderr.log").write_text(result.stderr)
    put(output / f"{label}.json", {"returncode": result.returncode, "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()})
    event(events, label, state="complete", returncode=result.returncode)
    if result.returncode:
        raise RuntimeError(f"{label}_failed_{result.returncode}")


def transfer_checkpoint(ip: str, output: Path, events: Path) -> None:
    event(events, "checkpoint_transfer", state="start")
    remote = "sudo install -d -o glmrunner -g glmrunner /home/glmrunner/gemma-safe-code/checkpoint && tar -C /home/glmrunner/gemma-safe-code/checkpoint -xf -"
    ssh = ["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", f"glmrunner@{ip}", remote]
    tar = subprocess.Popen(["tar", "-C", str(CHECKPOINT), "-cf", "-", "."], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    receiver = subprocess.run(ssh, stdin=tar.stdout, capture_output=True, timeout=2400)
    assert tar.stdout is not None
    tar.stdout.close()
    _, tar_stderr = tar.communicate(timeout=60)
    (output / "checkpoint_transfer.stderr.log").write_bytes(receiver.stderr + tar_stderr)
    put(output / "checkpoint_transfer.json", {"returncode": receiver.returncode, "stderr_sha256": hashlib.sha256(receiver.stderr + tar_stderr).hexdigest()})
    event(events, "checkpoint_transfer", state="complete", returncode=receiver.returncode)
    if receiver.returncode or tar.returncode:
        raise RuntimeError("checkpoint_transfer_failed")


def launch(ip: str, output: Path, events: Path, kv: str) -> None:
    invoke(ip, output, events, f"stop_{kv}", "sudo docker rm -f gemma-safe-code >/dev/null 2>&1 || true", 90)
    command = f"sudo docker run -d --name gemma-safe-code --gpus all --ipc=host --shm-size=16g --network host -v {REMOTE}:{REMOTE} {IMAGE} python3 -m sglang.launch_server --model-path {REMOTE}/checkpoint --tokenizer-path {REMOTE}/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype {kv} --served-model-name {MODEL} --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics"
    invoke(ip, output, events, f"start_{kv}", command, 180)
    for _ in range(90):
        result = run_ssh(ip, KEY, "curl -fsS http://127.0.0.1:30000/v1/models || true", timeout=30)
        if MODEL in result.stdout:
            event(events, f"ready_{kv}")
            return
        time.sleep(8)
    invoke(ip, output, events, f"logs_{kv}", "sudo docker logs gemma-safe-code || true", 120)
    raise RuntimeError(f"{kv}_readiness_timeout")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    if not os.getenv("INVOCATION_ID") or os.getenv("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise RuntimeError("durable_user_systemd_owner_required")
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=False)
    events = output / "events.jsonl"; ip = None
    try:
        for _ in range(30):
            ip = extract_public_ipv4(get_instance(args.instance_id) or {})
            if ip:
                break
            time.sleep(5)
        if not ip:
            raise RuntimeError("public_ip_unavailable")
        wait_ssh(ip, KEY, min(args.deadline_epoch - 900, time.time() + 600))
        invoke(ip, output, events, "bootstrap", "set -e; if ! command -v docker >/dev/null; then sudo apt-get update && sudo apt-get install -y docker.io; fi; sudo systemctl enable --now docker; if ! command -v nvidia-ctk >/dev/null; then curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg; curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null; sudo apt-get update; sudo apt-get install -y nvidia-container-toolkit; sudo nvidia-ctk runtime configure --runtime=docker; sudo systemctl restart docker; fi; docker --version; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", 1200)
        invoke(ip, output, events, "remote_dirs", f"mkdir -p {REMOTE}/suite {REMOTE}/run", 60)
        scp_to(ip, KEY, [PROJECT / "quality_runner.py", PROJECT / "safe_code_contract.py", PROJECT / "BINDINGS.json", PROJECT / "suite/cases.jsonl", PROJECT / "suite/policy.json", PROJECT / "suite/MANIFEST.json", PROJECT.parent / "sglang_v0512_h200_output_contract_adapter/adapter.py", REFERENCE, SCORER_DIR / "score_pair.py", SCORER_DIR / "validate_quality.py"], REMOTE + "/")
        invoke(ip, output, events, "layout_scripts", f"mv {REMOTE}/cases.jsonl {REMOTE}/suite/; mv {REMOTE}/policy.json {REMOTE}/suite/; mv {REMOTE}/MANIFEST.json {REMOTE}/suite/", 60)
        transfer_checkpoint(ip, output, events)
        invoke(ip, output, events, "checkpoint_verify", f"cd {REMOTE}/checkpoint && test $(find . -maxdepth 1 -type f | wc -l) -eq 8 && sha256sum model.safetensors.index.json", 180)
        invoke(ip, output, events, "image_pull", f"sudo docker pull {IMAGE}", 1200)
        env = f"BOUND_ADAPTER={REMOTE}/adapter.py BOUND_STRICT_SCORER={REMOTE}/score_pair.py ORIGINAL_SUITE={REMOTE}/suite"
        launch(ip, output, events, "bfloat16")
        invoke(ip, output, events, "control_capture", f"{env} python3 {REMOTE}/quality_runner.py capture --base http://127.0.0.1:30000 --output {REMOTE}/run/control.jsonl", 1800)
        invoke(ip, output, events, "control_persist", f"test -s {REMOTE}/run/control.jsonl && sha256sum {REMOTE}/run/control.jsonl", 60)
        launch(ip, output, events, "fp8_e5m2")
        invoke(ip, output, events, "candidate_capture", f"{env} python3 {REMOTE}/quality_runner.py capture --base http://127.0.0.1:30000 --output {REMOTE}/run/candidate.jsonl", 1800)
        invoke(ip, output, events, "remote_score", f"{env} python3 {REMOTE}/quality_runner.py score --control {REMOTE}/run/control.jsonl --candidate {REMOTE}/run/candidate.jsonl --output {REMOTE}/run/PAIRED_SCORE.json", 180)
        invoke(ip, output, events, "stop_for_reference", "sudo docker rm -f gemma-safe-code", 90)
        invoke(ip, output, events, "reference", f"sudo docker run --rm --gpus all -v {REMOTE}:{REMOTE} {IMAGE} python3 {REMOTE}/reference_sentinel.py {REMOTE} {REMOTE}/suite {REMOTE}/run/REFERENCE_SENTINEL.json", 1500)
        for name in ("control.jsonl", "candidate.jsonl", "PAIRED_SCORE.json", "REFERENCE_SENTINEL.json"):
            scp_from(ip, KEY, f"{REMOTE}/run/{name}", output / name)
        score = json.loads((output / "PAIRED_SCORE.json").read_text()); reference = json.loads((output / "REFERENCE_SENTINEL.json").read_text())
        control = next(json.loads(line) for line in (output / "control.jsonl").read_text().splitlines() if json.loads(line)["case_id"] == "teacher_nll")
        identity = reference["input_ids"][1:1 + min(len(control["raw_output"]["input_token_logprobs"]), len(reference["input_ids"]) - 1)] == [row["token_id"] for row in control["raw_output"]["input_token_logprobs"][:len(reference["input_ids"]) - 1]]
        terminal = {"classification": "safe_code_h200_paired_quality_terminal", "pass": bool(score["pass"] and identity and reference["scored_tokens"] >= 128), "paired_score": score, "reference_prompt_token_identity": identity, "reference_scored_tokens": reference["scored_tokens"], "raw_hashes": {"control": hashlib.sha256((output / "control.jsonl").read_bytes()).hexdigest(), "candidate": hashlib.sha256((output / "candidate.jsonl").read_bytes()).hexdigest()}, "server": {"ip": ip, "image": IMAGE, "model": MODEL}, "completed_at_utc": now()}
        put(output / "TERMINAL.json", terminal)
        put(output / "SUMMARY.json", {"classification": "complete", "pass": terminal["pass"], "terminal": "TERMINAL.json"})
        return 0 if terminal["pass"] else 2
    except Exception as error:
        put(output / "FAILURE.json", {"classification": "safe_code_h200_quality_failure", "type": type(error).__name__, "message": str(error)[:4000], "instance_id": args.instance_id, "ip": ip, "timestamp": now()})
        put(output / "SUMMARY.json", {"classification": "failed", "pass": False, "failure": "FAILURE.json"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
