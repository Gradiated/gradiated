#!/usr/bin/env python3
"""Env v2 training experiments (2026-10-31 night), run as data becomes available (fbf8, system python; /opt/posthog-env/exp_v2).

Same methods as the v1 pipeline on the rebuilt task pipeline: train pool = SOUND tasks of loop rounds b16-b22
(validator, plus the Opus acceptance gate from b21 on), eval = test split rebuilt with the gate (batches/eval_v2).
Data: tr2_data (base Qwen x4 + Opus x1 captured), dagger loop; adapters ev2-*.

Methods (all LoRA r16 from base Qwen 3.8 27B via correct/train.sh, rows = exact served token ids):
  ev2-rft     rejection sampling: per train task the best judge-passed rollout of 4 base-Qwen samples (tr2_data qwen)
  ev2-opus    SFT on judge-passed Opus 5.5 rollouts (tr2_data opus, captured in Qwen's prompt format)
  ev2-dagger  fault-guided corrected traces (correction loop with judge v3h, hints spliced out) + first-try passes
  ev2-combo   ev2-rft rows + ev2-dagger corrected rows
Pass rule everywhere: judge v3h overall >= 7.5 and no material wrong/unsupported error in the final answer.
Then one eval bench on the frozen eval set: base Qwen + every trained adapter, 3 samples, interleaved (after the
baseline bench, which uses the same twin teams). Each stage is idempotent (skips when its output exists).

    python3 exp_v2_pipeline.py      (loops until every stage is done)
"""

from __future__ import annotations

import glob
import gzip
import json
import os
import subprocess
import time

E = "/opt/posthog-env/exp_v2"
R = "/opt/posthog-env/runner/bench"
OPD = "/opt/posthog-env/opd_env"
GPU_SETS = {"a": ("0,1", 29591), "b": ("2,7", 29592)}
LOG = open(f"{E}/pipeline.log", "a", buffering=1)


def log(msg: str) -> None:
    LOG.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def sh(cmd: str, logf: str) -> int:
    log(f"$ {cmd[:200]}")
    with open(logf, "a") as f:
        return subprocess.run(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT).returncode


def passes(r: dict | None) -> bool:
    return bool(r) and r.get("overall") is not None and r["overall"] >= 7.5 and r.get("material_wrong_final", 1) == 0 \
        and r.get("material_unsupported_final", 1) == 0


def rows_count(path: str) -> int:
    op = gzip.open if path.endswith(".gz") else open
    try:
        with op(path, "rt") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def train(name: str, data: list[str], gpus: str, port: int) -> subprocess.Popen:
    out = f"/opt/posthog-env/correct/sft/{name}"
    cmd = (f"cd /opt/posthog-env/correct && GPUS={gpus} PORT={port} NAME={name} DATA='{' '.join(data)}' sh train.sh && "
           f"curl -s -X POST localhost:18012/v1/load_lora_adapter -H 'Content-Type: application/json' "
           f"-d '{{\"lora_name\":\"{name}\",\"lora_path\":\"{out}/vllm\"}}'")
    log(f"train {name} on GPUs {gpus}: {data}")
    return subprocess.Popen(cmd, shell=True, stdout=open(f"{E}/train_{name}.log", "a"), stderr=subprocess.STDOUT)


def train_opus(name: str, rows: str) -> subprocess.Popen:
    """Opus chain rows (up to 110k tokens) train with opd_env/train.py on all four free GPUs (as qwen-sft-opus did)."""
    out = f"{OPD}/sft/{name}"
    cmd = (f"cd {OPD} && TRAIN_ONLY=1 EPOCHS=2 sh sft_k3.sh {name} {rows} a && "
           f"curl -s -X POST localhost:18012/v1/load_lora_adapter -H 'Content-Type: application/json' "
           f"-d '{{\"lora_name\":\"{name}\",\"lora_path\":\"{out}/vllm\"}}'")
    log(f"train {name} (opd_env/train.py, GPUs 0,1,2,7): {rows}")
    return subprocess.Popen(cmd, shell=True, stdout=open(f"{E}/train_{name}.log", "a"), stderr=subprocess.STDOUT)


def build_rft() -> str | None:
    out = f"{E}/data/rft"
    if os.path.exists(f"{out}/sft_pass.jsonl"):
        return f"{out}/sft_pass.jsonl"
    if not os.path.exists(f"{R}/tr2_data/report.json"):
        return None
    sh(f"python3 /opt/posthog-env/rft/build_rft.py --root {R}/tr2_data/qwen --k 4 --out {out} --no-fallback",
       f"{E}/build_rft.log")
    return f"{out}/sft_pass.jsonl" if os.path.exists(f"{out}/sft_pass.jsonl") else None


def build_opus() -> str | None:
    out = f"{E}/data/opus/rows.jsonl.gz"
    if os.path.exists(out):
        return out
    if not os.path.exists(f"{R}/tr2_data/report.json"):
        return None
    tag = "ev2opus"
    d = f"{OPD}/rollouts/{tag}"
    os.makedirs(d, exist_ok=True)
    keep = []
    for run in glob.glob(f"{R}/tr2_data/opus/runs/*/r0.json"):
        tid = run.split("/")[-2]
        cap = run[:-5] + ".cap.jsonl.gz"
        judge = f"{R}/tr2_data/opus/judge/{tid}.s0.json"
        if not os.path.exists(cap):
            continue
        for src, dst in ((run, f"{d}/{tid}__s0.json"), (cap, f"{d}/{tid}__s0.cap.jsonl.gz")):
            if not os.path.lexists(dst):
                os.symlink(src, dst)
        try:
            if passes(json.load(open(judge))):
                keep.append(f"{tag}/{tid}__s0")
        except (OSError, ValueError):
            pass
    open(f"{E}/data/opus_keep.txt", "w").write("\n".join(keep) + "\n")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    log(f"opus: {len(keep)} judge-passed captured rollouts")
    sh(f"cd {OPD} && python3 build_sft.py --tag {tag} --keep {E}/data/opus_keep.txt --out {out}", f"{E}/build_opus.log")
    return out if os.path.exists(out) else None


def dagger_done() -> bool:
    return os.path.exists(f"{E}/dagger/DONE") or (
        os.path.exists(f"{E}/dagger.log") and not any(
            "loop.py" in open(f"/proc/{p}/cmdline", "rb").read().decode(errors="replace")
            for p in os.listdir("/proc") if p.isdigit() and os.path.exists(f"/proc/{p}/cmdline"))
        and os.path.isdir(f"{E}/dagger/state") and len(os.listdir(f"{E}/dagger/state")) > 0)


def build_dagger() -> tuple[str, str] | None:
    data = f"{E}/dagger/data"
    if os.path.exists(f"{data}/sft_corrected.jsonl"):
        return f"{data}/sft_corrected.jsonl", f"{data}/sft_firsttry.jsonl"
    if not dagger_done():
        return None
    sh(f"cd /opt/posthog-env/correct && python3 build_sft.py --root {E}/dagger --validate 0", f"{E}/build_dagger.log")
    if os.path.exists(f"{data}/sft_corrected.jsonl"):
        return f"{data}/sft_corrected.jsonl", f"{data}/sft_firsttry.jsonl"
    return None


def main() -> None:
    os.makedirs(f"{E}/data", exist_ok=True)
    running: dict[str, subprocess.Popen] = {}
    slots = {"a": None, "b": None}
    done = set(n for n in ("ev2-rft", "ev2-dagger", "ev2-combo")
               if os.path.exists(f"/opt/posthog-env/correct/sft/{n}/vllm"))
    if os.path.exists(f"{OPD}/sft/ev2-opus/vllm"):
        done.add("ev2-opus")
    plans = []  # (name, data builder)
    while True:
        for k, p in list(slots.items()):
            if p is not None and p[1].poll() is not None:
                if not p[0].endswith("-gpu-b"):
                    log(f"train {p[0]} finished rc={p[1].returncode}")
                    if p[1].returncode == 0:
                        done.add(p[0])
                slots[k] = None
        wanted = []
        rft = build_rft()
        if rft and rows_count(rft) > 0:
            wanted.append(("ev2-rft", [rft]))
        op = build_opus()
        if op and rows_count(op) > 0:
            wanted.append(("ev2-opus", [op]))
        dg = build_dagger()
        if dg:
            wanted.append(("ev2-dagger", [x for x in dg if rows_count(x) > 0]))
            if rft:
                wanted.append(("ev2-combo", [rft, dg[0]]))
        busy = {p[0] for p in slots.values() if p}
        for name, data in wanted:
            if name in done or name in busy or not data:
                continue
            if name == "ev2-opus":  # needs all four GPUs: only when both slots are free
                if slots["a"] is None and slots["b"] is None:
                    proc = train_opus(name, data[0])
                    slots["a"] = (name, proc)
                    slots["b"] = ("ev2-opus-gpu-b", proc)
                    busy.add(name)
                continue
            free = next((k for k, v in slots.items() if v is None), None)
            if free is None:
                break
            gpus, port = GPU_SETS[free]
            slots[free] = (name, train(name, data, gpus, port))
            busy.add(name)
        trained = sorted(done)
        all_data_known = os.path.exists(f"{R}/tr2_data/report.json") and dagger_done()
        if all_data_known and not any(slots.values()) and trained and os.path.exists(f"{R}/ev2_baselines/report.json") \
                and not os.path.exists(f"{R}/ev2_adapters/report.json"):
            ids = f"{E}/eval_ids.json"
            arms = ",".join(["qwen"] + trained)
            for name in trained:  # training loads each adapter on :18012 only; the eval uses all four servers
                path = f"{OPD}/sft/{name}/vllm" if name == "ev2-opus" else f"/opt/posthog-env/correct/sft/{name}/vllm"
                for port in (18000, 18010, 18011, 18012):
                    sh(f"curl -s -X POST localhost:{port}/v1/load_lora_adapter -H 'Content-Type: application/json' "
                       f"-d '{{\"lora_name\":\"{name}\",\"lora_path\":\"{path}\"}}'", f"{E}/load_adapters.log")
            sh(f"cd /opt/posthog-env/runner && python3 bench_env.py --tag ev2_adapters "
               f"--tasks /opt/posthog-env/exp_v2/eval_tasks.jsonl "
               f"--task-ids-file {ids} --arms {arms} --samples 3 --max-turns 12 --wall-s 1500 --workers 40 "
               f"--ports 18000:8,18010:8,18011:8,18012:8 --judge-workers 8", f"{E}/eval_adapters.log")
            log("eval of adapters done")
            return
        time.sleep(120)


if __name__ == "__main__":
    main()
