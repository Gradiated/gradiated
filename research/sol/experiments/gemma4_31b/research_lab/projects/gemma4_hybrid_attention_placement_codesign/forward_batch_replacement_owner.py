#!/usr/bin/env python3
"""Same-claim, single-server repair owner for the preload-bound component."""
from __future__ import annotations

import json, os, pathlib, subprocess, sys, threading, time

ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
KEY = "/root/.config/nebius/glm-campaign/ssh_ed25519"
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
HOST = "89.169.109.132"
REMOTE = "/home/glmrunner/phase-selective-full-model-readmission-20260726"
ART = ROOT / "artifacts" / "forward-batch-replacement-20260726t0054z"
STATE = ROOT / "FORWARD_BATCH_REPLACEMENT_OWNER_STATE.json"
DEADLINE = "2026-07-26T01:15:00Z"


def atomic(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True)


def ssh(command: str) -> subprocess.CompletedProcess[str]:
    return run(["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}",
                "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15",
                f"glmrunner@{HOST}", command])


def pool(action: str) -> None:
    run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action,
         "--project", PROJECT, "--bench", BENCH])


def save(name: str, result: subprocess.CompletedProcess[str]) -> None:
    (ART / f"{name}.stdout.log").write_text(result.stdout)
    (ART / f"{name}.stderr.log").write_text(result.stderr)


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    threading.Thread(target=lambda: [pool("heartbeat") for _ in iter(lambda: not stop.wait(75), False)], daemon=True).start()
    atomic(STATE, {"phase": "preload_bound_replacement", "deadline_utc": DEADLINE,
                   "artifact_root": str(ART), "bench": BENCH, "science_started": False})
    sources = [ROOT / n for n in ("sitecustomize.py", "forward_batch_dual_cache_driver.py",
                                  "full_model_memory_adapter.py", "phase_selective_full_model_remote.py")]
    manifest = {p.name: __import__("hashlib").sha256(p.read_bytes()).hexdigest() for p in sources}
    atomic(ART / "source_manifest.json", manifest)
    prep = ssh(f"set -eu; mkdir -p {REMOTE}/artifact {REMOTE}/source; test -d /home/glmrunner/phase-selective-full-model-v2/checkpoint")
    save("remote_prepare", prep)
    if prep.returncode:
        atomic(STATE, {"phase":"repair_ready","failure":"remote_prepare_failed","science_started":False,"artifact_root":str(ART),"deadline_utc":DEADLINE})
        return 2
    copy = run(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", *map(str, sources), f"glmrunner@{HOST}:{REMOTE}/source/"])
    save("source_copy", copy)
    if copy.returncode:
        atomic(STATE, {"phase":"repair_ready","failure":"source_copy_failed","science_started":False,"artifact_root":str(ART),"deadline_utc":DEADLINE})
        return 2
    atomic(STATE, {"phase":"replace_server","deadline_utc":DEADLINE,"artifact_root":str(ART),"source_manifest":manifest,"science_started":False})
    launch = ssh(f"set -eu; sudo -n docker stop phase-selective-readmission >/dev/null; sudo -n docker rm phase-selective-readmission >/dev/null; sudo -n docker run -d --name phase-selective-readmission --gpus all -p 30000:30000 -v {REMOTE}:/work -v /home/glmrunner/phase-selective-full-model-v2/checkpoint:/models/target:ro -w /work -e PYTHONPATH=/work/source gemma4-dflash-sglang:588d1f7bc942 python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --speculative-algorithm NGRAM --speculative-num-steps 12 --speculative-num-draft-tokens 12 --skip-server-warmup")
    save("replacement_launch", launch)
    if launch.returncode:
        atomic(STATE, {"phase":"repair_ready","failure":"replacement_launch_failed","science_started":False,"artifact_root":str(ART),"deadline_utc":DEADLINE})
        return 2
    for _ in range(100):
        proof = ssh(f"set -eu; cat {REMOTE}/artifact/adapter_attach.json; cat {REMOTE}/artifact/forward_batch_dual_cache.json; sudo -n docker inspect -f '{{{{.State.Running}}}}' phase-selective-readmission")
        save("preload_proof", proof)
        if proof.returncode == 0 and '"attached": true' in proof.stdout and '"installed": true' in proof.stdout:
            atomic(STATE, {"phase":"preload_proof_complete","deadline_utc":DEADLINE,"artifact_root":str(ART),"remote":REMOTE,"proof":proof.stdout,"science_started":False,"next":"component submission requires actual dual-bank/proxy implementation"})
            return 0
        time.sleep(3)
    logs = ssh("sudo -n docker logs phase-selective-readmission 2>&1 || true")
    save("replacement_server", logs)
    atomic(STATE, {"phase":"repair_ready","failure":"preload_proof_missing","science_started":False,"artifact_root":str(ART),"deadline_utc":DEADLINE})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
