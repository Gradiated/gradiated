"""Phase A driver: rounds of sample + teacher score -> LoRA update -> hot-load into vLLM, with periodic judged evals.

Round k samples with adapter k (the base model for k = 0), trains adapter k+1 from it, converts it to vLLM's module
names and loads it into the running Qwen server as <name>-<k+1>. Every --eval-every rounds the new adapter is
evaluated on the 300 test points with the judge, in the background. Re-running resumes after the last finished step.
Progress lines go to <run>/progress.jsonl.

    opd_loop.py --name opd-k3 --rounds 20
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path("/opt/posthog-sft")
OPD = ROOT / "opd"
SERVE_PY = ROOT / "serve-env/bin/python"
ACCELERATE = ROOT / "train-env/bin/accelerate"
VLLM = "http://127.0.0.1:18000/v1"


def vllm_post(path: str, body: dict) -> str:
    request = urllib.request.Request(f"{VLLM}/{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return response.read().decode()
    except urllib.error.HTTPError as error:
        return f"HTTP {error.code}: {error.read().decode()[:200]}"


def loaded() -> set[str]:
    with urllib.request.urlopen(f"{VLLM}/models", timeout=60) as response:
        return {m["id"] for m in json.load(response)["data"]}


def log(run: Path, record: dict) -> None:
    record = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **record}
    with open(run / "progress.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--prefixes", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--minibatches", type=int, default=2)
    p.add_argument("--gpus", default="0,1,2,3,5,6,7")
    p.add_argument("--eval-every", type=int, default=5)
    p.add_argument("--base", default="qwen27b-base")
    p.add_argument("--score-args", default="", help="extra opd_sample_score.py arguments, space-separated")
    p.add_argument("--port", default="29541", help="accelerate main process port; distinct per concurrent run")
    p.add_argument("--train-args", default="", help="extra opd_train.py arguments, space-separated")
    p.add_argument("--judge-via", default="proxy", choices=("proxy", "openai"),
                   help="judge transport for checkpoint evals; proxy uses the CLIProxyAPI subscription proxy on 127.0.0.1:8317")
    args = p.parse_args()

    run = OPD / "runs" / args.name
    (run / "rounds").mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HF_HOME": str(ROOT / "hf"), "PYTHONPATH": str(ROOT / "root_agent/pydeps")}
    evals: dict[str, subprocess.Popen] = {}

    def model_name(k: int) -> str:
        return args.base if k == 0 else f"{args.name}-{k:03d}"

    def ensure_loaded(k: int) -> None:
        if k > 0 and model_name(k) not in loaded():
            result = vllm_post("load_lora_adapter", {"lora_name": model_name(k), "lora_path": str(run / "vllm" / f"{k:03d}")})
            log(run, {"event": "load", "adapter": model_name(k), "result": result[:120]})

    for k in range(args.rounds):
        if (run / "adapters" / f"{k + 1:03d}" / "optimizer.pt").exists():
            continue
        ensure_loaded(k)
        batch = run / "rounds" / f"round-{k:03d}.jsonl"
        if not batch.with_suffix(".summary.json").exists():
            subprocess.run([str(SERVE_PY), str(OPD / "opd_sample_score.py"), "--round", str(k), "--student", model_name(k),
                            "--prefixes", str(args.prefixes), "--samples", str(args.samples), "--out", str(batch),
                            *args.score_args.split()],
                           check=True, env=env, cwd=OPD)
        summary = json.loads(batch.with_suffix(".summary.json").read_text())
        log(run, {"event": "round", **summary})

        train = [str(ACCELERATE), "launch", "--num_processes", str(len(args.gpus.split(","))), "--main_process_port", args.port,
                 str(OPD / "opd_train.py"), "--batch", str(batch), "--adapter-out", str(run / "adapters" / f"{k + 1:03d}"),
                 "--lr", str(args.lr), "--minibatches", str(args.minibatches), "--seed", str(k), *args.train_args.split()]
        if k > 0:
            train += ["--adapter-in", str(run / "adapters" / f"{k:03d}")]
        with open(run / "train.log", "a") as out:
            subprocess.run(train, check=True, env={**env, "CUDA_VISIBLE_DEVICES": args.gpus}, cwd=OPD, stdout=out, stderr=subprocess.STDOUT)
        train_log = json.loads((run / "adapters" / f"{k + 1:03d}" / "train_log.json").read_text())
        log(run, {"event": "train", "round": k, "rows": train_log["rows"], "steps": train_log["log"]})

        subprocess.run([str(SERVE_PY), str(ROOT / "vllm_adapter.py"), str(run / "adapters" / f"{k + 1:03d}"),
                        str(run / "vllm" / f"{k + 1:03d}")], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        ensure_loaded(k + 1)
        evals = {m: proc for m, proc in evals.items() if proc.poll() is None}
        if k > 0 and model_name(k) not in evals:
            vllm_post("unload_lora_adapter", {"lora_name": model_name(k)})
        for m in [m for m in loaded() if m.startswith(f"{args.name}-") and m not in evals and m != model_name(k + 1)]:
            vllm_post("unload_lora_adapter", {"lora_name": m})

        if (k + 1) % args.eval_every == 0:
            name = model_name(k + 1)
            with open(run / f"eval-{name}.log", "w") as out:
                evals[name] = subprocess.Popen(
                    ["python3", "run_eval.py", "data/test_v2.jsonl", "--n", "300", "--seed", "0", "--workers", "8",
                     "--judge-rpm", "60", "--judge-via", args.judge_via, "--provider", "vllm", "--model", name, "--base-url", VLLM],
                    cwd=ROOT / "eval", env=env, stdout=out, stderr=subprocess.STDOUT)
            log(run, {"event": "eval_started", "model": name})

    for name, proc in evals.items():
        proc.wait()
        log(run, {"event": "eval_done", "model": name, "exit": proc.returncode})


if __name__ == "__main__":
    main()
