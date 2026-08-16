#!/usr/bin/env python3
"""Bind public GPQA-Diamond and tau-bench inputs into paired capture assets."""

import ast
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "assets" / "source"
OUT = ROOT / "assets" / "requests"
ARTIFACT = ROOT / "artifacts" / "offline-bind-20260720"
TAU_COMMIT = "59a200c6d575d595120f1cb70fea53cef0632f6b"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def gpqa_requests() -> list[dict]:
    path = SOURCE / "gpqa" / "gpqa_diamond.csv"
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    required = {"Question", "Correct Answer", "Incorrect Answer 1", "Incorrect Answer 2", "Incorrect Answer 3", "Record ID"}
    if len(rows) != 198 or not required.issubset(rows[0]):
        raise RuntimeError(f"unexpected GPQA-Diamond shape: {len(rows)} rows")
    result = []
    for i, row in enumerate(rows):
        choices = [row["Correct Answer"], row["Incorrect Answer 1"], row["Incorrect Answer 2"], row["Incorrect Answer 3"]]
        result.append({
            "case_id": f"gpqa-diamond-{i:03d}-{row['Record ID']}",
            "benchmark": "GPQA-Diamond",
            "messages": [{"role": "user", "content": row["Question"].strip()}],
            "choices": choices,
            "expected_answer": row["Correct Answer"].strip(),
            "source_record_id": row["Record ID"],
        })
    return result


def tau_tasks() -> list[dict]:
    result = []
    for domain, filename in (("airline", "airline_tasks.py"), ("retail", "retail_tasks.py")):
        tree = ast.parse((SOURCE / "tau_bench" / filename).read_text(encoding="utf-8"), filename=filename)
        assignment = next((n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "tasks" for t in n.targets)), None)
        if assignment is None:
            raise RuntimeError(f"missing tasks assignment in {filename}")
        tasks = ast.literal_eval(assignment.value)
        for i, task in enumerate(tasks):
            result.append({
                "case_id": f"taubench-{domain}-{i:03d}",
                "benchmark": "TauBench",
                "domain": domain,
                "user_id": task.get("user_id"),
                "messages": [{"role": "user", "content": task["instruction"]}],
                "expected_actions": task.get("actions", []),
                "expected_outputs": task.get("outputs", []),
                "source_commit": TAU_COMMIT,
                "source_file": filename,
            })
    if not result or any(not row["messages"][0]["content"] for row in result):
        raise RuntimeError("empty or malformed TauBench task set")
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    gpqa = gpqa_requests()
    tau = tau_tasks()
    write_jsonl(OUT / "gpqa_diamond_requests.jsonl", gpqa)
    write_jsonl(OUT / "taubench_requests.jsonl", tau)
    source_files = sorted(p for p in SOURCE.rglob("*") if p.is_file())
    request_files = sorted(p for p in OUT.rglob("*") if p.is_file())
    manifest = {
        "schema_version": 1,
        "status": "pass",
        "provenance": {
            "gpqa_url": "https://openaipublic.blob.core.windows.net/simple-evals/gpqa_diamond.csv",
            "gpqa_license_reference": "https://github.com/idavidrein/gpqa/blob/main/LICENSE",
            "taubench_url": "https://github.com/sierra-research/tau-bench",
            "taubench_commit": TAU_COMMIT,
        },
        "counts": {"gpqa_diamond": len(gpqa), "taubench": len(tau), "taubench_airline": sum(r["domain"] == "airline" for r in tau), "taubench_retail": sum(r["domain"] == "retail" for r in tau)},
        "source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in source_files},
        "request_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in request_files},
        "pairing": {
            "arms": ["bf16_control", "dynamic_fp8_candidate"],
            "same_case_order": True,
            "same_runtime": "sglang-v0.5.13",
            "same_checkpoint_revision": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "capture_path": "/v1/chat/completions",
            "tool_path_required": True,
            "deterministic_seed": 0,
            "candidate_weight_mode": "dynamic in-memory fp8_e4m3fn linears",
            "control_weight_mode": "bfloat16",
            "kv_cache": "fp8_e5m2",
            "nondeterministic_tau_replay": "record exact tool traces and environment snapshot; score task success from traces",
        },
    }
    manifest_path = ARTIFACT / "BINDING_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    terminal = {
        "schema_version": 1,
        "terminal": "offline_quality_assets_bound",
        "pass": True,
        "manifest": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": sha256(manifest_path),
        "raw_capture_files": [str(p.relative_to(ROOT)) for p in request_files],
        "scientific_invocation_started": False,
        "provider_spend_usd": 0.0,
    }
    terminal_path = ARTIFACT / "OFFLINE_BINDING_TERMINAL.json"
    terminal_path.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"terminal": str(terminal_path), "terminal_sha256": sha256(terminal_path), "counts": manifest["counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
