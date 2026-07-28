#!/usr/bin/env python3
"""Untimed stock-path diagnostic/guard; consumes only explicitly named rows."""
import argparse, json, os, time, urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("FRESH_ENDPOINT_ROOT", ".")).resolve()
WORKLOAD = ROOT / "artifacts/fresh-endpoint/FRESH_WORKLOAD.jsonl"

def post(body):
    payload = {"input_ids": body["prompt"], "sampling_params": {"temperature": 0, "max_new_tokens": body["max_tokens"], "min_new_tokens": body["min_tokens"], "ignore_eos": body["ignore_eos"]}}
    req = urllib.request.Request("http://127.0.0.1:30000/generate", json.dumps(payload, separators=(",", ":")).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as response:
        answer = json.loads(response.read())
    meta = answer.get("meta_info") or {}
    usage = {"prompt_tokens": meta.get("prompt_tokens", len(body["prompt"])), "completion_tokens": meta.get("completion_tokens", body["max_tokens"])}
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return {"output_ids": answer.get("output_ids") or meta.get("output_ids") or meta.get("completion_token_ids"), "finish_reason": meta.get("finish_reason") or answer.get("finish_reason"), "usage": usage}

def wait_ready():
    deadline = time.monotonic() + 720
    while time.monotonic() < deadline:
        try:
            data = json.loads(urllib.request.urlopen("http://127.0.0.1:30000/v1/models", timeout=4).read())
            if any(x.get("id") == "google/gemma-4-31B-it" for x in data.get("data", [])):
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("server_not_ready")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--indices", nargs="+", type=int, required=True); ap.add_argument("--output", required=True)
    args = ap.parse_args(); rows = {json.loads(x)["fresh_index"]: json.loads(x) for x in WORKLOAD.read_text().splitlines()}
    wait_ready(); results = []
    for index in args.indices:
        row = rows[index]; started = time.time()
        try:
            answer = post(row["request_body"]); results.append({"fresh_index": index, "source_i": row["source_i"], "request_sha256": row["request_sha256"], "ok": True, "elapsed_s": time.time()-started, **answer})
        except Exception as exc:
            results.append({"fresh_index": index, "source_i": row["source_i"], "request_sha256": row["request_sha256"], "ok": False, "elapsed_s": time.time()-started, "error": repr(exc)})
    out = {"schema_version": 1, "indices": args.indices, "results": results, "all_ok": all(x["ok"] for x in results)}
    p = Path(args.output); p.parent.mkdir(parents=True, exist_ok=True); part = p.with_suffix(p.suffix+".part"); part.write_text(json.dumps(out, indent=2, sort_keys=True)+"\n"); part.replace(p)
    if not out["all_ok"]: raise SystemExit(2)

if __name__ == "__main__": main()
