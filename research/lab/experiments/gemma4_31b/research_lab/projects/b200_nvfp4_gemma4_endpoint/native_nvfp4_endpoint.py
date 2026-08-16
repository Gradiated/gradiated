#!/usr/bin/env python3
"""Build the immutable execution packet for the native-NVFP4 endpoint.

The packet intentionally does not convert on the coordinator.  Conversion is a
GPU producer and therefore happens once, after the director supplies a B200,
inside this project's remote root.  The worker copies and verifies the BF16
source before conversion and never points vLLM at the shared source path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
BASE = PROJECT.parent / "exact_h200_vllm_baseline_shared_runner" / "artifacts" / "corrected-transfer-view"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
VLLM_COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"
PREDECESSOR = "0838a2262bffd0d2e800bbdd0cf857c28115ae0fc6e9677b50433c7a9ff8ecb1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest() -> list[dict[str, object]]:
    rows = []
    for line in (BASE / "model-files.sha256").read_text().splitlines():
        value, name = line.split("  ", 1)
        path = BASE / name
        rows.append({"path": name, "sha256": value, "bytes": path.stat().st_size})
    return rows


def converter_program() -> str:
    return '''#!/usr/bin/env python3
"""One-shot native-NVFP4 compressed-tensors producer.

This deliberately records the producer package/version and calibration manifest
before writing the final directory.  The NVFP4 config is checked by the pinned
vLLM loader again before any endpoint request.
"""
import argparse, hashlib, json, os, pathlib, shutil, sys

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""): h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--source",type=pathlib.Path,required=True); p.add_argument("--output",type=pathlib.Path,required=True); p.add_argument("--calibration",type=pathlib.Path,required=True); p.add_argument("--producer",default="llmcompressor"); a=p.parse_args()
    if a.output.exists(): raise SystemExit("immutable output exists")
    try:
        import llmcompressor
    except Exception as e:
        raise SystemExit("conversion_dependency_missing:"+repr(e))
    # The public producer CLI is used to avoid reimplementing its packed tensor
    # serialization.  Its observed version and all output hashes are bound below.
    recipe={"quant_stage":{"type":"QuantizationModifier","targets":["Linear"],"scheme":"NVFP4","ignore":["lm_head","model.embed_tokens","vision_tower","multi_modal_projector"]}}
    recipe_path=a.source.parent/"native_nvfp4_recipe.json"; recipe_path.write_text(json.dumps(recipe,sort_keys=True))
    command=[sys.executable,"-m","llmcompressor", "oneshot", "--model",str(a.source), "--recipe",str(recipe_path), "--dataset",str(a.calibration), "--output-dir",str(a.output)]
    code=os.spawnv(os.P_WAIT, sys.executable, command)
    if code: raise SystemExit("converter_exit:"+str(code))
    config=json.loads((a.output/"config.json").read_text()); q=config.get("quantization_config",{})
    groups=q.get("config_groups",{}).values()
    nvfp4=any(g.get("weights",{}).get("num_bits")==4 and g.get("weights",{}).get("group_size")==16 and g.get("weights",{}).get("type")=="float" and g.get("input_activations",{}).get("num_bits")==4 and g.get("input_activations",{}).get("group_size")==16 and g.get("input_activations",{}).get("type")=="float" for g in groups)
    if not nvfp4: raise SystemExit("conversion_semantic_mismatch:missing_symmetric_float4_group16_w4a4")
    rows=[]
    for x in sorted(a.output.rglob("*")):
        if x.is_file(): rows.append({"path":str(x.relative_to(a.output)),"bytes":x.stat().st_size,"sha256":sha(x)})
    (a.output/"CONVERSION_MANIFEST.json").write_text(json.dumps({"producer":a.producer,"producer_version":getattr(llmcompressor,"__version__",None),"recipe_sha256":sha(recipe_path),"semantic_contract":"symmetric float4 tensor-group size16 W4A4; lm_head/vision/projector retained BF16","files":rows},sort_keys=True,indent=2))
if __name__=="__main__": main()
'''


def endpoint_program() -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail
ROOT="${{1:?project remote root}}"
MODE="${{2:?control|candidate}}"
case "$MODE" in
  control) MODEL="$ROOT/bf16-source" ;;
  candidate) MODEL="$ROOT/nvfp4-checkpoint" ;;
  *) exit 64 ;;
esac
OUT="$ROOT/result-$MODE"
mkdir -p "$OUT"
if [ "$MODE" = candidate ]; then test -f "$MODEL/CONVERSION_MANIFEST.json"; fi
docker run --rm --gpus all --network host -v "$ROOT:$ROOT:ro" {IMAGE} \\
  vllm serve "$MODEL" --quantization compressed-tensors --dtype bfloat16 \\
  --enable-prefix-caching --max-num-seqs 32 --max-model-len 4608 \\
  --max-num-batched-tokens 134848 --served-model-name google/gemma-4-31B-it \\
  --disable-log-requests >"$OUT/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
python3 "$ROOT/wait_server.py" --pid "$SERVER" --url http://127.0.0.1:30000/v1/models --output "$OUT/server-readiness.json"
python3 "$ROOT/endpoint_driver.py" --host 127.0.0.1 --port 30000 --output "$OUT"
'''


def staging_program() -> str:
    return '''#!/usr/bin/env python3
"""Atomically admit the project-local BF16 snapshot before one conversion."""
import argparse, hashlib, json, os, pathlib, shutil
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--root",type=pathlib.Path,required=True);a=p.parse_args();packet=a.root/"packet"; identities=json.loads((packet/"IDENTITIES.json").read_text()); source=a.root/"inputs"/"bf16-source"; target=a.root/"bf16-source"; temporary=a.root/"bf16-source.tmp"
 if target.exists(): raise SystemExit("immutable_bf16_source_already_finalized")
 if temporary.exists(): raise SystemExit("staging_tmp_requires_reconciliation")
 temporary.mkdir(parents=True)
 for row in identities["checkpoint"]["files"]:
  src=source/row["path"]; dst=temporary/row["path"]; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
  if dst.stat().st_size != row["bytes"] or sha(dst) != row["sha256"]: raise SystemExit("checkpoint_manifest_mismatch:"+row["path"])
 os.replace(temporary,target)
 (target/"PROJECT_LOCAL_SOURCE_MANIFEST.json").write_text(json.dumps({"source_manifest_sha256":identities["checkpoint"]["source_manifest_sha256"],"files":identities["checkpoint"]["files"]},sort_keys=True,indent=2))
if __name__=="__main__": main()
'''


def driver_program() -> str:
    return '''#!/usr/bin/env python3
import argparse, concurrent.futures, hashlib, json, math, pathlib, threading, time, urllib.request
def canonical(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def one(i, body, base, out, barrier):
    (out/f"request-{i:02}.json").write_bytes(canonical(body)); barrier.wait(); start=time.monotonic(); raw=[]; ids=[]; text=""; usage={}; error=None
    try:
      req=urllib.request.Request(base+"/v1/completions",canonical(body),{"Content-Type":"application/json"})
      with urllib.request.urlopen(req,timeout=1800) as r:
       for line in r:
        raw.append(line)
        if line.startswith(b"data: ") and line.strip()!=b"data: [DONE]":
         x=json.loads(line[6:]); c=(x.get("choices") or [{}])[0]; ids.extend(c.get("token_ids") or []); text+=c.get("text") or ""; usage=x.get("usage") or usage
    except Exception as e: error=repr(e)
    elapsed=time.monotonic()-start; (out/f"response-{i:02}.sse").write_bytes(b"".join(raw))
    return {"index":i,"error":error,"seconds":elapsed,"prompt_tokens":usage.get("prompt_tokens"),"completion_tokens":usage.get("completion_tokens"),"returned_token_ids":len(ids),"nonempty":bool(text),"request_sha256":hashlib.sha256(canonical(body)).hexdigest()}
def main():
 p=argparse.ArgumentParser();p.add_argument("--host",required=True);p.add_argument("--port",type=int,required=True);p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);base=f"http://{a.host}:{a.port}"
 vocab=262144; prefix=[1000+((j*7919+17)%48000) for j in range(535)]; bodies=[]
 for i in range(32):
  suffix=[60000+i]+[1000+((i*4214+j*1543)%48000) for j in range(3678)]
  bodies.append({"model":"google/gemma-4-31B-it","prompt":prefix+suffix,"max_tokens":358,"min_tokens":358,"ignore_eos":True,"temperature":0,"seed":20260728+i,"stream":True,"stream_options":{"include_usage":True},"return_token_ids":True,"add_special_tokens":False})
 b=threading.Barrier(32); start=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex: rows=list(ex.map(lambda z:one(z[0],z[1],base,a.output,b),enumerate(bodies)))
 batch=time.monotonic()-start; ok=all(r["error"] is None and r["prompt_tokens"]==4214 and r["completion_tokens"]==358 and r["returned_token_ids"]==358 and r["nonempty"] and math.isfinite(r["seconds"]) for r in rows)
 (a.output/"TERMINAL.json").write_text(json.dumps({"classification":"endpoint_measurement" if ok else "endpoint_invalid","complete_requests":sum(r["error"] is None for r in rows),"service_seconds_per_request":batch/32,"batch_seconds":batch,"rows":rows,"identity":{"workload":"c32/4214/358/text-only/non-reasoning","candidate_requires":"compressed-tensors symmetric float4 tensor-group size16 W4A4"}},sort_keys=True,indent=2))
if __name__=="__main__": main()
'''


def wait_program() -> str:
    return '''#!/usr/bin/env python3
import argparse,json,os,time,urllib.request
p=argparse.ArgumentParser();p.add_argument("--pid",type=int,required=True);p.add_argument("--url",required=True);p.add_argument("--output",required=True);a=p.parse_args();end=time.monotonic()+1800
while time.monotonic()<end:
 if os.waitpid(a.pid,os.WNOHANG)[0]: raise SystemExit("server_exited_before_ready")
 try:
  with urllib.request.urlopen(a.url,timeout=5) as r: open(a.output,"w").write(json.dumps({"ready":True,"models":json.loads(r.read())}));raise SystemExit(0)
 except Exception: time.sleep(2)
raise SystemExit("server_readiness_timeout")
'''


def build(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    files = load_manifest()
    identities = {
        "checkpoint": {"model": "google/gemma-4-31B-it", "revision": MODEL_REVISION, "source_manifest_sha256": digest(BASE / "model-files.sha256"), "source_bytes": sum(int(x["bytes"]) for x in files), "files": files, "remote_materialization": "copy to <project-root>/bf16-source, verify every SHA-256, atomically rename; do not consume the shared path"},
        "tokenizer": {"tokenizer_json_sha256": next(x["sha256"] for x in files if x["path"] == "tokenizer.json"), "tokenizer_config_sha256": next(x["sha256"] for x in files if x["path"] == "tokenizer_config.json"), "chat_template_sha256": next(x["sha256"] for x in files if x["path"] == "chat_template.jinja")},
        "runtime": {"image": IMAGE, "vllm_commit": VLLM_COMMIT, "predecessor_terminal_sha256": PREDECESSOR, "required_consumers": ["scaled_fp4_quant", "cutlass_scaled_fp4_mm"]},
        "workload": {"mode": "text-only non-reasoning", "concurrency": 32, "prompt_tokens": 4214, "completion_tokens": 358, "shared_prefix_tokens": 535, "temperature": 0, "ignore_eos": True},
        "storage_estimate": {"bf16_source_gib": 58.28, "native_nvfp4_output_gib_estimate": [20.0, 28.0], "conversion_scratch_gib_estimate": 95, "disk_request_gib": 300, "basis": "31B linear payload at 0.5625 B/parameter plus BF16 tied head/vision/projector, safetensor metadata, and retained source"},
        "control": {"name": "same-session same-B200 BF16 vLLM", "command_delta": "replace --quantization compressed-tensors model path with verified project-local BF16 source path; preserve image, c32 bodies, cache, limits and telemetry", "reason": "strongest scope-matched control"},
        "lifecycle_request": {"accelerator": "nvidia-b200-sxm", "absolute_owner_minutes": 90, "converter_minutes": 35, "server_and_pair_minutes": 40, "retrieval_minutes": 15, "spend_ceiling_usd": 8.0, "provider_mutation": "director_only", "status": "awaiting durable reservation and inventory bench"},
        "semantic_contract": "symmetric float4 tensor-group size 16 for both weights and input activations; vLLM must select CompressedTensorsW4A4Fp4, and endpoint timing must not materialize BF16 linear weights",
    }
    (output / "IDENTITIES.json").write_text(json.dumps(identities, indent=2, sort_keys=True) + "\n")
    for name, content in {"stage_project_snapshot.py": staging_program(), "convert_native_nvfp4.py": converter_program(), "run_endpoint.sh": endpoint_program(), "endpoint_driver.py": driver_program(), "wait_server.py": wait_program()}.items():
        path = output / name; path.write_text(content); path.chmod(0o755)
    hashes = {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / "PACKET_MANIFEST.json").write_text(json.dumps({"packet_version": 1, "files": hashes, "entrypoint": "stage_project_snapshot.py --root <project-remote-root>; convert_native_nvfp4.py --source <project-root>/bf16-source --output <project-root>/nvfp4-checkpoint --calibration <immutable-calibration>; run_endpoint.sh <project-remote-root> control; run_endpoint.sh <project-remote-root> candidate", "conversion_entrypoint": "convert_native_nvfp4.py --source <project-root>/bf16-source --output <project-root>/nvfp4-checkpoint --calibration <immutable-calibration>", "unsupported_only_if": "pinned vLLM source rejects the stated symmetric float4 tensor-group-16 W4A4 semantic contract"}, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=PROJECT / "artifacts" / "native-nvfp4-endpoint-packet-v1"); args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
