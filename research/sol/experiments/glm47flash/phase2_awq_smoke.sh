#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/phase2-awq-smoke
PUBLIC=/workspace/public
MODEL=/workspace/model-awq
HTTP=
TELEMETRY=
DCGM=
SERVER=

mkdir -p "$OUT" "$PUBLIC"

phase() {
  printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"
}

package_artifact() {
  python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path("/workspace/phase2-awq-smoke")
manifest = [
    {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    for path in sorted(root.rglob("*"))
    if path.is_file()
]
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
  tar -C /workspace -czf "$PUBLIC/phase2-awq-smoke.tar.gz.tmp" phase2-awq-smoke
  mv "$PUBLIC/phase2-awq-smoke.tar.gz.tmp" "$PUBLIC/phase2-awq-smoke.tar.gz"
  sha256sum "$PUBLIC/phase2-awq-smoke.tar.gz" > "$PUBLIC/phase2-awq-smoke.tar.gz.sha256"
}

finish() {
  rc=$?
  set +e
  phase teardown begin
  [ -n "$SERVER" ] && kill -TERM "$SERVER" 2>/dev/null
  [ -n "$DCGM" ] && kill -TERM "$DCGM" 2>/dev/null
  [ -n "$TELEMETRY" ] && kill -TERM "$TELEMETRY" 2>/dev/null
  [ -n "$SERVER" ] && wait "$SERVER" 2>/dev/null
  [ -n "$DCGM" ] && wait "$DCGM" 2>/dev/null
  [ -n "$TELEMETRY" ] && wait "$TELEMETRY" 2>/dev/null
  nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1
  phase teardown complete
  package_artifact
  if [ "$rc" -eq 0 ]; then
    printf 'READY\n' > "$PUBLIC/STATUS"
  else
    printf 'FAILED\n' > "$PUBLIC/STATUS"
  fi
  wait "$HTTP"
}

trap finish EXIT
printf 'BOOTSTRAP\n' > "$PUBLIC/STATUS"
python3 -m http.server 8000 --bind 0.0.0.0 --directory "$PUBLIC" > "$OUT/http.stdout.log" 2> "$OUT/http.stderr.log" &
HTTP=$!

phase allocation_bootstrap begin
uname -a > "$OUT/uname.txt"
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt" 2>&1
python3 -m pip freeze > "$OUT/pip-freeze.txt"
phase allocation_bootstrap complete

(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" &
TELEMETRY=$!

if command -v dcgmi >/dev/null; then
  dcgmi dmon -l > "$OUT/dcgm-fields.txt" 2>&1 || true
  timeout 2400 dcgmi dmon -e 1002,1003,1004,1005,1009,1010,1011,1012 -d 1000 > "$OUT/dcgm.csv" 2> "$OUT/dcgm.stderr.log" &
  DCGM=$!
else
  printf 'dcgmi unavailable\n' > "$OUT/dcgm-unavailable.txt"
fi

phase dependency_and_patch begin
printf '%s' "$PATCHER_GZ_B64" | base64 -d | gzip -d > /tmp/patch_sglang_awq_loader.py
python3 /tmp/patch_sglang_awq_loader.py /sgl-workspace/sglang > "$OUT/runtime-patch.json"
timeout 120 python3 - <<'PY' > "$OUT/native-import.json"
import hashlib
import inspect
import json
from pathlib import Path

import cutlass
import sglang
import torch
import transformers
from sglang.srt.layers.quantization.compressed_tensors.schemes.compressed_tensors_wNa16 import CompressedTensorsWNA16
from sglang.srt.layers.quantization.compressed_tensors.schemes.compressed_tensors_wNa16_moe import CompressedTensorsWNA16MoE
from sglang.srt.models.glm4_moe_lite import Glm4MoeLiteForCausalLM

model_source = Path(inspect.getfile(Glm4MoeLiteForCausalLM))
capability = torch.cuda.get_device_capability()
capability_int = capability[0] * 10 + capability[1]
minimum_capability = max(
    CompressedTensorsWNA16.get_min_capability(),
    CompressedTensorsWNA16MoE.get_min_capability(),
)
if capability_int < minimum_capability:
    raise SystemExit(
        f"GPU capability {capability_int} is below Marlin minimum {minimum_capability}"
    )
print(
    json.dumps(
        {
            "class": Glm4MoeLiteForCausalLM.__name__,
            "model_source_sha256": hashlib.sha256(model_source.read_bytes()).hexdigest(),
            "sglang": sglang.__version__,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "transformers": transformers.__version__,
            "gpu_name": torch.cuda.get_device_name(),
            "gpu_compute_capability": capability,
            "marlin_minimum_capability": minimum_capability,
        },
        indent=2,
    )
)
PY
phase dependency_and_patch complete

phase model_download begin
python3 - <<'PY' > "$OUT/model-download.log" 2>&1
from huggingface_hub import HfApi, snapshot_download

revision = "ab31d120fbe79988fe2a0259993cf3c222aa8881"
info = HfApi().model_info("cyankiwi/GLM-4.7-Flash-AWQ-4bit", revision=revision)
if info.sha != revision:
    raise SystemExit(f"revision mismatch: {info.sha}")
print("resolved_revision=" + info.sha)
print(
    snapshot_download(
        "cyankiwi/GLM-4.7-Flash-AWQ-4bit",
        revision=revision,
        local_dir="/workspace/model-awq",
    )
)
PY
sha256sum "$MODEL/config.json" "$MODEL/model.safetensors.index.json" > "$OUT/model-hashes.sha256"
grep -q '^079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9 ' "$OUT/model-hashes.sha256"
grep -q '^b9c53433e94f2fe7870cdbc3fcb6ed1431eb500c5242a039de93fef4bb988695 ' "$OUT/model-hashes.sha256"
du -sb "$MODEL" > "$OUT/model-size.txt"
phase model_download complete

phase checkpoint_metadata_gate begin
python3 - <<'PY' > "$OUT/checkpoint-metadata-gate.json"
import json
from pathlib import Path

from safetensors import safe_open

model = Path("/workspace/model-awq")
shard = model / "model-00001-of-00004.safetensors"
names = {
    "q_shape": "model.layers.1.self_attn.q_a_proj.weight_shape",
    "kv_shape": "model.layers.1.self_attn.kv_a_proj_with_mqa.weight_shape",
    "q_packed": "model.layers.1.self_attn.q_a_proj.weight_packed",
    "kv_packed": "model.layers.1.self_attn.kv_a_proj_with_mqa.weight_packed",
    "q_scale": "model.layers.1.self_attn.q_a_proj.weight_scale",
    "kv_scale": "model.layers.1.self_attn.kv_a_proj_with_mqa.weight_scale",
}
with safe_open(shard, framework="pt", device="cpu") as handle:
    tensors = {key: handle.get_tensor(name) for key, name in names.items()}
q_shape = tensors["q_shape"]
kv_shape = tensors["kv_shape"]
if q_shape.tolist() != [768, 2048] or kv_shape.tolist() != [576, 2048]:
    raise SystemExit("unexpected q/kv weight_shape metadata")
if list(tensors["q_packed"].shape) != [768, 256] or list(tensors["kv_packed"].shape) != [576, 256]:
    raise SystemExit("unexpected packed weight layout")
if list(tensors["q_scale"].shape) != [768, 64] or list(tensors["kv_scale"].shape) != [576, 64]:
    raise SystemExit("unexpected group-32 scale layout")
print(
    json.dumps(
        {
            "tensor_names": names,
            "q_weight_shape": q_shape.tolist(),
            "kv_weight_shape": kv_shape.tolist(),
            "expected_fused_weight_shape": [1344, 2048],
            "packed_shapes": [list(tensors["q_packed"].shape), list(tensors["kv_packed"].shape)],
            "scale_shapes": [list(tensors["q_scale"].shape), list(tensors["kv_scale"].shape)],
            "zero_points_present": False,
        },
        indent=2,
    )
)
PY
phase checkpoint_metadata_gate complete

phase model_load begin
CMD=(
  python3 -m sglang.launch_server
  --model-path "$MODEL"
  --served-model-name glm-4.7-flash-awq
  --model-impl sglang
  --quantization compressed-tensors
  --host 127.0.0.1
  --port 30000
  --context-length 4096
  --max-running-requests 1
  --max-total-tokens 4096
  --max-prefill-tokens 4096
  --mem-fraction-static 0.80
  --chunked-prefill-size 4096
  --cuda-graph-backend-decode disabled
  --cuda-graph-backend-prefill disabled
  --disable-radix-cache
  --disable-shared-experts-fusion
  --tool-call-parser glm47
  --reasoning-parser glm45
  --enable-metrics
  --enable-request-time-stats-logging
  --random-seed 1234
)
printf '%q ' "${CMD[@]}" > "$OUT/server-command.txt"
"${CMD[@]}" > "$OUT/server.stdout.log" 2> "$OUT/server.stderr.log" &
SERVER=$!
healthy=0
# Cold 20.19 GB checkpoint reads measured 321.64 s for the first of four
# parallel shards on attempt 3. This is model-load time, not provider startup.
for _ in $(seq 1 600); do
  if ! kill -0 "$SERVER" 2>/dev/null; then
    wait "$SERVER"
    exit $?
  fi
  if curl -fsS http://127.0.0.1:30000/health >/dev/null; then
    healthy=1
    break
  fi
  sleep 2
done
[ "$healthy" -eq 1 ]
nvidia-smi -q > "$OUT/nvidia-smi-loaded.txt" 2>&1
phase model_load complete

phase warmup begin
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-before.txt"
phase warmup complete

phase deterministic_completion begin
REQ='{"model":"glm-4.7-flash-awq","messages":[{"role":"user","content":"Return a JSON object with alpha equal to 17 and beta equal to smoke."}],"temperature":0,"max_tokens":64,"seed":20260713}'
printf '%s\n' "$REQ" > "$OUT/request.json"
for i in 1 2; do
  kill -0 "$SERVER"
  curl -fsS -H 'Content-Type: application/json' -d "$REQ" http://127.0.0.1:30000/v1/chat/completions > "$OUT/response-$i.json"
done
python3 - <<'PY' > "$OUT/determinism.json"
import hashlib
import json
from pathlib import Path

from transformers import AutoTokenizer

root = Path("/workspace/phase2-awq-smoke")
responses = [json.loads((root / f"response-{index}.json").read_text()) for index in (1, 2)]
messages = [response["choices"][0]["message"] for response in responses]
normalized = [
    {key: message.get(key) for key in ("content", "reasoning_content", "tool_calls")}
    for message in messages
]
if normalized[0] != normalized[1]:
    raise SystemExit("greedy response mismatch")
tokenizer = AutoTokenizer.from_pretrained("/workspace/model-awq")
serialized = json.dumps(normalized[0], sort_keys=True, ensure_ascii=False)
token_ids = tokenizer.encode(serialized, add_special_tokens=False)
print(
    json.dumps(
        {
            "exact_normalized_identity": True,
            "normalized_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
            "token_ids": token_ids,
            "usage": [response.get("usage") for response in responses],
        },
        indent=2,
    )
)
PY
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-after.txt"
phase deterministic_completion complete

# Fail-closed smoke artifact comes first. A throughput restart is a separate
# allocation only after native load and deterministic output are proven.
exit 0

phase throughput_server_restart begin
kill -TERM "$SERVER"
wait "$SERVER" 2>/dev/null || true
SERVER=
CMD_SCREEN=(
  python3 -m sglang.launch_server
  --model-path "$MODEL"
  --served-model-name glm-4.7-flash-awq
  --model-impl sglang
  --quantization compressed-tensors
  --host 127.0.0.1
  --port 30000
  --context-length 4096
  --max-running-requests 8
  --max-total-tokens 32768
  --max-prefill-tokens 24576
  --mem-fraction-static 0.85
  --chunked-prefill-size 4096
  --cuda-graph-backend-decode disabled
  --cuda-graph-backend-prefill disabled
  --disable-radix-cache
  --disable-shared-experts-fusion
  --tool-call-parser glm47
  --reasoning-parser glm45
  --enable-metrics
  --enable-request-time-stats-logging
  --random-seed 1234
)
printf '%q ' "${CMD_SCREEN[@]}" > "$OUT/throughput-server-command.txt"
"${CMD_SCREEN[@]}" > "$OUT/throughput-server.stdout.log" 2> "$OUT/throughput-server.stderr.log" &
SERVER=$!
healthy=0
for _ in $(seq 1 240); do
  if ! kill -0 "$SERVER" 2>/dev/null; then
    wait "$SERVER"
    exit $?
  fi
  if curl -fsS http://127.0.0.1:30000/health >/dev/null; then
    healthy=1
    break
  fi
  sleep 2
done
[ "$healthy" -eq 1 ]
phase throughput_server_restart complete

phase throughput_screen begin
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/throughput-metrics-before.txt"
python3 - <<'PY' > "$OUT/throughput-screen.json"
import concurrent.futures
import json
import math
import statistics
import time
import urllib.request

from transformers import AutoTokenizer

MODEL = "/workspace/model-awq"
URL = "http://127.0.0.1:30000/v1/completions"
INPUT_TOKENS = 3072
OUTPUT_TOKENS = 384
CONCURRENCY = 8
REQUESTS = 16

tokenizer = AutoTokenizer.from_pretrained(MODEL)
candidate = tokenizer.encode(" code", add_special_tokens=False)
if len(candidate) != 1:
    raise SystemExit("single-token prompt atom unavailable")
prompt = tokenizer.decode(candidate * INPUT_TOKENS)
if len(tokenizer.encode(prompt, add_special_tokens=False)) != INPUT_TOKENS:
    raise SystemExit("prompt token round-trip mismatch")

request_definition = {
    "model": "glm-4.7-flash-awq",
    "prompt": prompt,
    "temperature": 0,
    "max_tokens": OUTPUT_TOKENS,
    "ignore_eos": True,
    "seed": 20260713,
    "stream": True,
    "stream_options": {"include_usage": True},
}


def percentile(values, quantile):
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def run_one(index):
    started = time.perf_counter()
    first_token_at = None
    chunk_times = []
    text = []
    usage = None
    request = urllib.request.Request(
        URL,
        data=json.dumps(request_definition).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        for raw_line in response:
            line = raw_line.decode(errors="replace").strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            event = json.loads(payload)
            if event.get("usage"):
                usage = event["usage"]
            choices = event.get("choices") or []
            token_text = choices[0].get("text", "") if choices else ""
            if token_text:
                now = time.perf_counter()
                if first_token_at is None:
                    first_token_at = now
                chunk_times.append(now)
                text.append(token_text)
    ended = time.perf_counter()
    completion = "".join(text)
    measured_output = len(tokenizer.encode(completion, add_special_tokens=False))
    output_count = (usage or {}).get("completion_tokens", measured_output)
    input_count = (usage or {}).get("prompt_tokens", INPUT_TOKENS)
    intervals = [right - left for left, right in zip(chunk_times, chunk_times[1:])]
    return {
        "index": index,
        "input_tokens": input_count,
        "output_tokens": output_count,
        "ttft_seconds": None if first_token_at is None else first_token_at - started,
        "e2e_seconds": ended - started,
        "mean_inter_chunk_seconds": statistics.mean(intervals) if intervals else None,
        "chunks": len(chunk_times),
    }


wall_started = time.perf_counter()
errors = []
results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
    futures = {executor.submit(run_one, index): index for index in range(REQUESTS)}
    for future in concurrent.futures.as_completed(futures):
        try:
            results.append(future.result())
        except Exception as error:
            errors.append({"index": futures[future], "error": repr(error)})
wall_seconds = time.perf_counter() - wall_started
if errors:
    raise SystemExit(json.dumps({"errors": errors}))
if any(result["output_tokens"] != OUTPUT_TOKENS for result in results):
    raise SystemExit("screen did not produce the requested output token count")

ttft = [result["ttft_seconds"] for result in results]
e2e = [result["e2e_seconds"] for result in results]
inter_chunk = [
    result["mean_inter_chunk_seconds"]
    for result in results
    if result["mean_inter_chunk_seconds"] is not None
]
total_input = sum(result["input_tokens"] for result in results)
total_output = sum(result["output_tokens"] for result in results)
print(
    json.dumps(
        {
            "classification": "measured 4K-context economic screen, not matched 8K/1K headline",
            "seed": 20260713,
            "requests": REQUESTS,
            "concurrency": CONCURRENCY,
            "declared_input_tokens_per_request": INPUT_TOKENS,
            "declared_output_tokens_per_request": OUTPUT_TOKENS,
            "actual_total_input_tokens": total_input,
            "actual_total_output_tokens": total_output,
            "wall_seconds": wall_seconds,
            "request_throughput_per_second": REQUESTS / wall_seconds,
            "input_tokens_per_second": total_input / wall_seconds,
            "output_tokens_per_second": total_output / wall_seconds,
            "total_tokens_per_second": (total_input + total_output) / wall_seconds,
            "error_rate": 0.0,
            "ttft_seconds": {
                "p50": percentile(ttft, 0.50),
                "p95": percentile(ttft, 0.95),
                "p99": percentile(ttft, 0.99),
            },
            "e2e_seconds": {
                "p50": percentile(e2e, 0.50),
                "p95": percentile(e2e, 0.95),
                "p99": percentile(e2e, 0.99),
            },
            "mean_inter_chunk_seconds": {
                "p50": percentile(inter_chunk, 0.50),
                "p95": percentile(inter_chunk, 0.95),
                "p99": percentile(inter_chunk, 0.99),
            },
            "results": sorted(results, key=lambda item: item["index"]),
            "request_definition": {
                key: value for key, value in request_definition.items() if key != "prompt"
            },
            "prompt_sha256": __import__("hashlib").sha256(prompt.encode()).hexdigest(),
        },
        indent=2,
    )
)
PY
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/throughput-metrics-after.txt"
phase throughput_screen complete

phase packaging begin
phase packaging complete
