#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, "/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
from stock_control import run_ssh, scp_from

KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
IP = "89.169.122.202"
REMOTE = "/home/glmrunner/gemma-safe-code"
IMAGE = "docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temp.replace(path)


def command(out, label, value, timeout):
    result = run_ssh(IP, KEY, value, timeout=timeout)
    (out / f"{label}.stdout.log").write_text(result.stdout)
    (out / f"{label}.stderr.log").write_text(result.stderr)
    put(out / f"{label}.json", {"returncode": result.returncode, "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()})
    if result.returncode:
        raise RuntimeError(f"{label}_failed_{result.returncode}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not os.getenv("INVOCATION_ID") or os.getenv("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise RuntimeError("durable_user_systemd_owner_required")
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=False)
    try:
        for name in ("control.jsonl", "candidate.jsonl", "PAIRED_SCORE.json"):
            scp_from(IP, KEY, f"{REMOTE}/run/{name}", out / name)
        score = json.loads((out / "PAIRED_SCORE.json").read_text())
        if score.get("classification") != "safe_code_paired_quality_score" or score.get("pass") is not False:
            raise ValueError("expected persisted typed negative paired score")
        command(out, "stop_server_for_reference", "sudo docker rm -f gemma-safe-code", 90)
        command(out, "direct_reference", f"sudo docker run --rm --gpus all -v {REMOTE}:{REMOTE} {IMAGE} python3 {REMOTE}/reference_sentinel.py {REMOTE} {REMOTE}/suite {REMOTE}/run/REFERENCE_SENTINEL.json", 1500)
        scp_from(IP, KEY, f"{REMOTE}/run/REFERENCE_SENTINEL.json", out / "REFERENCE_SENTINEL.json")
        reference = json.loads((out / "REFERENCE_SENTINEL.json").read_text())
        control = next(json.loads(line) for line in (out / "control.jsonl").read_text().splitlines() if json.loads(line)["case_id"] == "teacher_nll")
        observed = [value["token_id"] for value in control["raw_output"]["input_token_logprobs"]]
        expected = reference["input_ids"][1:1 + min(len(observed), len(reference["input_ids"]) - 1)]
        identity = expected == observed[:len(expected)]
        terminal = {"classification": "safe_code_h200_paired_quality_terminal", "pass": False, "negative_reason": "heldout_ordering_failed_in_both_arms", "paired_score": score, "reference_prompt_token_identity": identity, "reference_scored_tokens": reference["scored_tokens"], "raw_hashes": {"control": digest(out / "control.jsonl"), "candidate": digest(out / "candidate.jsonl")}, "reference_sha256": digest(out / "REFERENCE_SENTINEL.json"), "completed_at_utc": now(), "server_state_after": "stopped_for_direct_transformers_reference; image, checkpoint, and caches retained"}
        put(out / "TERMINAL.json", terminal)
        put(out / "SUMMARY.json", {"classification": "complete_negative_quality_terminal", "pass": False, "terminal": "TERMINAL.json"})
    except Exception as error:
        put(out / "FAILURE.json", {"classification": "safe_code_terminal_completion_failure", "type": type(error).__name__, "message": str(error)[:4000], "timestamp": now()})
        raise


if __name__ == "__main__":
    main()
