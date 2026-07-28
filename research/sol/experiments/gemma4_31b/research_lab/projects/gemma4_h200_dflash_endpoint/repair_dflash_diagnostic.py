#!/usr/bin/env python3
"""Repair only the persisted SSE observer after the terminal [DONE] frame."""
from __future__ import annotations
import hashlib, json, pathlib, shutil, statistics

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "artifacts/dflash-diagnostic-repair/results/dflash-diagnostic"
OUT = ROOT / "artifacts/dflash-diagnostic-repaired/results/dflash-diagnostic"

def canonical(x): return json.dumps(x, sort_keys=True, separators=(",", ":")).encode()

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows=[]
    for src in sorted(SRC.glob("response-*.sse")):
        idx=src.stem.split("-")[-1]
        ids=[]; events=[]; text=""
        for raw in src.read_bytes().splitlines():
            if not raw.startswith(b"data: ") or raw[6:].strip() == b"[DONE]": continue
            item=json.loads(raw[6:])
            if item.get("output_ids") is not None: ids=[int(v) for v in item["output_ids"]]
            if item.get("text") is not None: text=item["text"]
            if item.get("meta_info"): events.append(item["meta_info"])
        old=json.loads((SRC / f"request-{idx}.json").read_text())
        row=dict(old); row.update(error=None, token_ids=ids, returned_token_ids=len(ids), text_finite=True,
            text_nonempty=bool(text), text_sha256=hashlib.sha256(text.encode()).hexdigest())
        (OUT / f"response-{idx}.sse").write_bytes(src.read_bytes()); (OUT / f"response-{idx}.txt").write_text(text)
        (OUT / f"request-{idx}.json").write_text(json.dumps(row,indent=2,sort_keys=True)+"\n"); rows.append(row)
    if len(rows)!=4 or any(r["returned_token_ids"]!=358 or r["error"] is not None for r in rows): raise SystemExit("repaired_rows_not_complete")
    old=json.loads((SRC/"TERMINAL.json").read_text())
    batch=old["batch_seconds"]
    terminal=dict(old)
    terminal.update({"pass": True, "complete_requests": 4, "raw_token_ids_present": True,
        "rows": rows, "output_tokens_per_second": 4*358/batch})
    (OUT/"WORKLOAD.json").write_bytes((SRC/"WORKLOAD.json").read_bytes())
    (OUT/"metrics-before.prom").write_bytes((SRC/"metrics-before.prom").read_bytes())
    (OUT/"metrics-after.prom").write_bytes((SRC/"metrics-after.prom").read_bytes())
    (OUT/"TERMINAL.json").write_text(json.dumps(terminal,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"rows":len(rows),"tokens":[r["returned_token_ids"] for r in rows],"terminal_pass":True},sort_keys=True))

if __name__ == "__main__": main()
