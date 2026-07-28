#!/usr/bin/env python3
"""Run the bound sequential BF16/FP8 quality capture on the retained H200."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import pathlib
import random
import re
import subprocess
import time
import urllib.request

ROOT = pathlib.Path(__import__("os").environ.get("QUALITY_ROOT", "/home/glmrunner/gemma-kernel-frontier"))
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
MODEL = "google/gemma-4-31B-it"
CHECKPOINT = "/work/checkpoint"
PORT = 30000


def canon(x: object) -> bytes:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(x: bytes) -> str:
    return hashlib.sha256(x).hexdigest()


def write(path: pathlib.Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    tmp.replace(path)


def post(path: str, body: object, timeout: int = 240) -> tuple[dict, bytes, float]:
    raw = canon(body)
    started = time.monotonic()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", raw, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
    return json.loads(data), data, time.monotonic() - started


def server(arm: str, audit: pathlib.Path) -> str:
    name = f"gemma4-quality-{arm}"
    subprocess.run(["sudo", "docker", "rm", "-f", name], capture_output=True, check=False)
    args = [
        "--model-path", CHECKPOINT, "--tokenizer-path", CHECKPOINT,
        "--served-model-name", MODEL, "--dtype", "bfloat16", "--tp-size", "1",
        "--kv-cache-dtype", "fp8_e5m2", "--host", "0.0.0.0", "--port", str(PORT),
        "--context-length", "5000", "--max-running-requests", "32", "--mem-fraction-static", "0.85",
        "--enable-metrics", "--skip-server-warmup", "--enable-dynamic-chunking",
        "--chunked-prefill-size", "2048", "--enable-fused-qk-norm-rope", "--cuda-graph-max-bs", "32",
        "--prefill-attention-backend", "triton", "--decode-attention-backend", "triton", "--page-size", "1",
        "--num-continuous-decode-steps", "1", "--triton-attention-num-kv-splits", "8",
    ]
    if arm == "fp8":
        args += ["--quantization", "fp8"]
        entry = ["python3", "/work/quality-input/proven_v0513_endpoint_entrypoint.py"]
    else:
        entry = ["python3", "-m", "sglang.launch_server"]
    env = ["-e", f"FP8_MODULE_AUDIT=/work/quality-artifacts/{arm}/fp8-modules.jsonl", "-e", f"FP8_CONSUMER_AUDIT=/work/quality-artifacts/{arm}/fp8-consumers.jsonl", "-e", f"FP8_RUNTIME_AUDIT=/work/quality-artifacts/{arm}/fp8-runtime.json"]
    cmd = ["sudo", "docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc=host", "--network", "host", "-v", f"{ROOT}:/work", *env, IMAGE, *entry, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"server_start_{arm}:{result.stderr[-1000:]}")
    (audit / "container-id").write_text(result.stdout)
    for _ in range(180):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/models")
            with urllib.request.urlopen(req, timeout=10) as response:
                if MODEL in response.read().decode(errors="replace"):
                    return name
        except Exception:
            pass
        time.sleep(5)
    subprocess.run(["sudo", "docker", "logs", name], stdout=(audit / "server.log").open("w"), stderr=subprocess.STDOUT, check=False)
    raise RuntimeError(f"server_not_ready_{arm}")


def stop(name: str) -> None:
    subprocess.run(["sudo", "docker", "rm", "-f", name], capture_output=True, check=False)


def capture_case(case_id: str, body: dict, destination: pathlib.Path) -> dict:
    response, raw, elapsed = post("/v1/chat/completions", body)
    row = {"case_id": case_id, "request": body, "request_sha256": sha_bytes(canon(body)), "raw_response": response, "raw_response_bytes_sha256": sha_bytes(raw), "elapsed_seconds": elapsed}
    with destination.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return row


def feature_cases() -> list[dict]:
    tool = {"type": "function", "function": {"name": "lookup_user", "description": "Look up a user by id.", "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}}
    return [
        {"case_id": "feature-ready", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Reply with exactly READY."}], "temperature": 0, "max_tokens": 16}},
        {"case_id": "feature-json", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Return only JSON with key status and value ok."}], "temperature": 0, "max_tokens": 32, "response_format": {"type": "json_object"}}},
        {"case_id": "feature-tool", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Use the lookup_user tool for user_id demo_user."}], "tools": [tool], "tool_choice": "required", "temperature": 0, "max_tokens": 64}},
    ]


def nll_case() -> dict:
    text = ("The Gemma production validation sentence contains stable teacher forced evidence. " * 40).strip()
    return {"text": text, "sampling_params": {"temperature": 0, "max_new_tokens": 1}, "return_logprob": True, "logprob_start_len": 0, "top_logprobs_num": 0}


def gpqa_cases(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    result = []
    for i, row in enumerate(rows):
        choices = [row["Correct Answer"], row["Incorrect Answer 1"], row["Incorrect Answer 2"], row["Incorrect Answer 3"]]
        random.Random(20260720 + i).shuffle(choices)
        letters = "ABCD"
        prompt = row["Question"].strip() + "\n\nChoices:\n" + "\n".join(f"{letters[j]}. {x.strip()}" for j, x in enumerate(choices)) + "\nAnswer with only the letter."
        result.append({"case_id": f"gpqa-diamond-{i:03d}-{row['Record ID']}", "body": {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 8}, "correct_letter": letters[choices.index(row["Correct Answer"])], "choices": choices})
    return result


def tau_cases(root: pathlib.Path) -> list[dict]:
    result = []
    for domain, filename in (("airline", "airline_tasks.py"), ("retail", "retail_tasks.py")):
        text = (root / "quality-input" / filename).read_text(encoding="utf-8")
        tree = ast.parse(text, filename=filename)
        assign = next(n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "tasks" for t in n.targets))
        tasks = ast.literal_eval(assign.value)
        for i, task in enumerate(tasks):
            tools = []
            for action in task.get("actions", []):
                name = action["name"]
                tools.append({"type": "function", "function": {"name": name, "description": f"Perform {name}.", "parameters": {"type": "object", "additionalProperties": True}}})
            result.append({"case_id": f"taubench-{domain}-{i:03d}", "body": {"model": MODEL, "messages": [{"role": "user", "content": task["instruction"]}], "tools": tools, "temperature": 0, "max_tokens": 256}, "expected_actions": [a["name"] for a in task.get("actions", [])]})
    return result


def score_feature(rows: list[dict]) -> dict:
    passed = []
    for row in rows:
        msg = ((row["raw_response"].get("choices") or [{}])[0].get("message") or {})
        content = msg.get("content") or ""
        if row["case_id"] == "feature-ready": ok = content.strip() == "READY"
        elif row["case_id"] == "feature-json":
            try: ok = json.loads(content.strip("`json\n")) == {"status": "ok"}
            except Exception: ok = False
        else: ok = bool(msg.get("tool_calls")) and msg["tool_calls"][0].get("function", {}).get("name") == "lookup_user"
        passed.append({"case_id": row["case_id"], "pass": ok, "content": content, "message": msg})
    return {"pass": all(x["pass"] for x in passed), "rows": passed}


def score_gpqa(rows: list[dict], cases: list[dict]) -> dict:
    by_id = {x["case_id"]: x for x in cases}; scored = []
    for row in rows:
        text = (((row["raw_response"].get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip().upper()
        match = re.search(r"\b([ABCD])\b", text)
        answer = match.group(1) if match else None
        scored.append({"case_id": row["case_id"], "answer": answer, "expected": by_id[row["case_id"]]["correct_letter"], "pass": answer == by_id[row["case_id"]]["correct_letter"]})
    return {"count": len(scored), "accuracy": sum(x["pass"] for x in scored) / len(scored), "rows": scored}


def score_tau(rows: list[dict], cases: list[dict]) -> dict:
    by_id = {x["case_id"]: x for x in cases}; scored = []
    for row in rows:
        msg = ((row["raw_response"].get("choices") or [{}])[0].get("message") or {})
        names = [x.get("function", {}).get("name") for x in (msg.get("tool_calls") or []) if isinstance(x, dict)]
        expected = by_id[row["case_id"]]["expected_actions"]
        scored.append({"case_id": row["case_id"], "expected_actions": expected, "observed_actions": names, "pass": names[:len(expected)] == expected})
    return {"count": len(scored), "task_success": sum(x["pass"] for x in scored) / len(scored), "rows": scored}


def run_arm(arm: str, root: pathlib.Path, gpqa: list[dict], tau: list[dict]) -> dict:
    audit = root / "quality-artifacts" / arm; audit.mkdir(parents=True, exist_ok=True)
    name = server(arm, audit)
    try:
        feature_path = root / "captures" / f"{arm}-feature.jsonl"; feature_path.parent.mkdir(exist_ok=True)
        features = [capture_case(x["case_id"], x["body"], feature_path) for x in feature_cases()]
        nll_response, nll_raw, nll_elapsed = post("/generate", nll_case())
        nll_values = (nll_response.get("meta_info") or {}).get("input_token_logprobs") or []
        nll = [{"logprob": float(v[0] if isinstance(v, list) else v["logprob"]), "token_id": int(v[1] if isinstance(v, list) else v["token_id"])} for v in nll_values if (v[0] if isinstance(v, list) else v.get("logprob")) is not None]
        write(root / "captures" / f"{arm}-nll.json", {"request": nll_case(), "response": nll_response, "response_sha256": sha_bytes(nll_raw), "elapsed_seconds": nll_elapsed, "input_token_logprobs": nll})
        gpqa_path = root / "captures" / f"{arm}-gpqa.jsonl"; gpqa_rows = [capture_case(x["case_id"], x["body"], gpqa_path) for x in gpqa]
        tau_path = root / "captures" / f"{arm}-tau.jsonl"; tau_rows = [capture_case(x["case_id"], x["body"], tau_path) for x in tau]
        result = {"arm": arm, "feature": score_feature(features), "nll_tokens": len(nll), "nll_mean": (-sum(x["logprob"] for x in nll) / len(nll)) if nll else math.inf, "gpqa": score_gpqa(gpqa_rows, gpqa), "taubench": score_tau(tau_rows, tau), "raw_hashes": {"feature": sha_bytes(feature_path.read_bytes()), "gpqa": sha_bytes(gpqa_path.read_bytes()), "tau": sha_bytes(tau_path.read_bytes())}, "fp8_audit": {"modules": str(audit / "fp8-modules.jsonl"), "consumers": str(audit / "fp8-consumers.jsonl"), "runtime": str(audit / "fp8-runtime.json")}}
        write(root / "captures" / f"{arm}-RESULT.json", result)
        return result
    finally:
        stop(name)


def existing_arm(arm: str, root: pathlib.Path, gpqa: list[dict], tau: list[dict]) -> dict:
    capture = root / "captures"
    feature_rows = [json.loads(x) for x in (capture / f"{arm}-feature.jsonl").read_text().splitlines() if x.strip()]
    gpqa_rows = [json.loads(x) for x in (capture / f"{arm}-gpqa.jsonl").read_text().splitlines() if x.strip()]
    tau_rows = [json.loads(x) for x in (capture / f"{arm}-tau.jsonl").read_text().splitlines() if x.strip()]
    nll_doc = json.loads((capture / f"{arm}-nll.json").read_text())
    nll = nll_doc.get("input_token_logprobs") or []
    audit = root / "quality-artifacts" / arm
    result = {"arm": arm, "feature": score_feature(feature_rows), "nll_tokens": len(nll), "nll_mean": (-sum(x["logprob"] for x in nll) / len(nll)) if nll else math.inf, "gpqa": score_gpqa(gpqa_rows, gpqa), "taubench": score_tau(tau_rows, tau), "raw_hashes": {"feature": sha_bytes((capture / f"{arm}-feature.jsonl").read_bytes()), "gpqa": sha_bytes((capture / f"{arm}-gpqa.jsonl").read_bytes()), "tau": sha_bytes((capture / f"{arm}-tau.jsonl").read_bytes())}, "fp8_audit": {"modules": str(audit / "fp8-modules.jsonl"), "consumers": str(audit / "fp8-consumers.jsonl"), "runtime": str(audit / "fp8-runtime.json")}}
    write(capture / f"{arm}-RESULT.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=pathlib.Path, required=True); parser.add_argument("--resume-control", action="store_true"); args = parser.parse_args()
    root = args.root; root.mkdir(parents=True, exist_ok=True); (root / "captures").mkdir(exist_ok=True)
    write(root / "INVOCATION_STATE.json", {"control_scientific_started": True, "candidate_scientific_started": False})
    gpqa = gpqa_cases(ROOT / "quality-input" / "gpqa_diamond.csv"); tau = tau_cases(ROOT)
    control = existing_arm("bf16", root, gpqa, tau) if args.resume_control else run_arm("bf16", root, gpqa, tau)
    write(root / "INVOCATION_STATE.json", {"control_scientific_started": True, "candidate_scientific_started": True})
    candidate = run_arm("fp8", root, gpqa, tau)
    control_gate = control["feature"]["pass"] and control["nll_tokens"] >= 128
    candidate_gate = candidate["feature"]["pass"] and candidate["nll_tokens"] >= 128 and candidate["nll_mean"] - control["nll_mean"] <= 0.03
    terminal = {"schema_version": 1, "classification": "production_quality_capture_complete", "pass": control_gate and candidate_gate, "control": control, "candidate": candidate, "nll_delta": candidate["nll_mean"] - control["nll_mean"], "gates": {"control_feature_nll": control_gate, "candidate_feature_nll": candidate_gate}, "request_counts": {"gpqa_diamond": len(gpqa), "taubench": len(tau)}, "scientific_invocation": {"control": True, "candidate": True}}
    write(root / "TERMINAL.json", terminal); write(root / "WORKER_TERMINAL.json", {"schema_version": 1, "status": "terminal", "classification": "completed", "pass": terminal["pass"]})
    return 0 if terminal["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
