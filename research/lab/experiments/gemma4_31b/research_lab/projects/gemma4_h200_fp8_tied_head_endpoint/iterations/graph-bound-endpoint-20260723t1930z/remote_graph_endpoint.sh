#!/usr/bin/env bash
set -Eeuo pipefail

root=${FP8_HEAD_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/artifacts"
checkpoint=/home/glmrunner/gemma4-async-result-pipeline/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma-fp8-tied-head-graph-bound
port=30001
mkdir -p "$artifacts"

atomic_terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime
import json
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
temporary = path.with_suffix(path.suffix + ".part")
value = {
    "schema_version": 1,
    "status": "terminal",
    "classification": sys.argv[2],
    "message": sys.argv[3],
    "timestamp_utc": datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat().replace("+00:00", "Z"),
}
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(temporary, path)
PY
}

set_state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json
import os
import pathlib
import sys
import time

path = pathlib.Path(sys.argv[1])
temporary = path.with_suffix(path.suffix + ".part")
value = (
    json.loads(path.read_text())
    if path.exists()
    else {
        "candidate_cuda_started": False,
        "smoke_science_started": False,
        "endpoint_science_started": False,
        "endpoint_request_accepted": False,
    }
)
value[sys.argv[2]] = True
value["updated_unix_s"] = time.time()
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(temporary, path)
PY
}

fail() {
  atomic_terminal integration_failure "$1"
  exit 1
}

finalize() {
  set +e
  sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/container-inspect.json" 2>&1 || true
  nvidia-smi \
    --query-gpu=timestamp,name,memory.used,utilization.gpu,power.draw \
    --format=csv,noheader >"$artifacts/gpu-final.csv" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 \
    --numeric-owner -czf "$root/fp8-graph-endpoint-compact.tar.gz" \
    -C "$artifacts" .
  sha256sum "$root/fp8-graph-endpoint-compact.tar.gz" \
    >"$root/fp8-graph-endpoint-compact.tar.gz.sha256"
}
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic_terminal integration_failure "$BASH_COMMAND"' ERR

rm -rf "$artifacts"
mkdir -p "$artifacts/tied-head" "$artifacts/graph-boundary" \
  "$artifacts/runtime-audit"
test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 \
  || fail pinned_image_missing
sha256sum "$input"/stack/*.py "$input"/binding/* "$input"/source/*.py \
  >"$artifacts/input-sha256.txt"

# Both named predecessors are terminal campaign containers. The benchmark
# inventory remains authoritative for the bench itself.
sudo docker rm -f gemma-width-recovered-candidate \
  gemma-late30-width16384-candidate "$container" >/dev/null 2>&1 || true
set_state candidate_cuda_started
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -v "$checkpoint:/work/checkpoint:ro" \
  -v "$root:/work/fp8-graph-endpoint" \
  -e PYTHONPATH=/work/fp8-graph-endpoint/input/stack:/sgl-workspace/sglang/python \
  -e STACKED_FRONTIER_ARM=candidate -e RING_CACHE_ARM=candidate \
  -e RING_CACHE_AUDIT=/work/fp8-graph-endpoint/artifacts/runtime-audit/ring.jsonl \
  -e RING_CACHE_TRACE_TRANSITIONS=0 \
  -e RESIDUAL_CANDIDATE_AUDIT=/work/fp8-graph-endpoint/artifacts/runtime-audit/residual.jsonl \
  -e QKV_EPILOGUE_AUDIT=/work/fp8-graph-endpoint/artifacts/runtime-audit/qkv.jsonl \
  -e FP8_MODULE_AUDIT=/work/fp8-graph-endpoint/artifacts/runtime-audit/modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/fp8-graph-endpoint/artifacts/runtime-audit/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/fp8-graph-endpoint/artifacts/runtime-audit/runtime.json \
  -e FP8_TIED_HEAD_ARM=candidate -e FP8_TIED_HEAD_MODE=endpoint \
  -e FP8_TIED_HEAD_AUDIT=/work/fp8-graph-endpoint/artifacts/tied-head \
  -e FP8_GRAPH_BOUNDARY_AUDIT=/work/fp8-graph-endpoint/artifacts/graph-boundary \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" \
  python3 /work/fp8-graph-endpoint/input/stack/proven_v0513_endpoint_entrypoint.py \
    --model-path /work/checkpoint --tokenizer-path /work/checkpoint \
    --served-model-name google/gemma-4-31B-it --dtype bfloat16 \
    --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 \
    --host 0.0.0.0 --port "$port" --context-length 5000 \
    --max-running-requests 32 --mem-fraction-static 0.85 \
    --enable-metrics --skip-server-warmup --enable-dynamic-chunking \
    --chunked-prefill-size 2048 --enable-fused-qk-norm-rope \
    --cuda-graph-max-bs 32 --prefill-attention-backend triton \
    --decode-attention-backend triton --page-size 1 \
    --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8 \
    >"$artifacts/container-id"

ready=0
for _ in $(seq 1 180); do
  if curl -fsS "http://127.0.0.1:$port/v1/models" \
    >"$artifacts/models.json" 2>"$artifacts/models.stderr"; then
    ready=1
    break
  fi
  [[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == true ]] \
    || break
  sleep 4
done
sudo docker logs "$container" >"$artifacts/server-start.log" 2>&1 || true
[[ "$ready" == 1 ]] || fail candidate_server_not_ready
test -s "$artifacts/tied-head/representation.json" \
  || fail candidate_representation_absent
test -s "$artifacts/graph-boundary/SOURCE_BINDING.json" \
  || fail graph_source_binding_absent
test ! -e "$artifacts/tied-head/COMPONENT_RESULT.json" \
  || fail forbidden_component_replay

set +e
python3 - \
  "$input/binding/settled-representation.json" \
  "$artifacts/tied-head/representation.json" \
  "$artifacts/REPRESENTATION_ADMISSION.json" <<'PY'
import json
import pathlib
import sys

settled = json.load(open(sys.argv[1]))
observed = json.load(open(sys.argv[2]))
keys = [
    "candidate",
    "embedding",
    "embedding_preserved",
    "materialized_dequantized_weight",
    "output_weight",
    "separate_storage",
    "weight_nonfinite_count",
    "weight_saturation_count",
    "weight_saturation_fraction",
    "weight_scale",
    "weight_scale_granularity",
]
matching = {key: observed.get(key) == settled.get(key) for key in keys}
value = {
    "schema_version": 1,
    "pass": all(matching.values()),
    "matching_fields": matching,
    "settled_component_replayed": False,
    "settled_weight_scale_reused": True,
}
pathlib.Path(sys.argv[3]).write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n"
)
raise SystemExit(0 if value["pass"] else 20)
PY
representation_rc=$?
set -e
if [[ "$representation_rc" -eq 20 ]]; then
  atomic_terminal representation_reject settled_e4m3_representation_mismatch
  exit 0
elif [[ "$representation_rc" -ne 0 ]]; then
  fail representation_admission_harness_failed
fi

# This smoke is the only pre-endpoint quality workload. It both tests the
# unchanged token path and creates decode graph replays for the boundary audit.
set_state smoke_science_started
set +e
python3 - "$port" "$artifacts/SEMANTIC_SMOKE.json" <<'PY'
import json
import pathlib
import sys
import urllib.request

port = int(sys.argv[1])
cases = [
    ("json", 'Return only a JSON object with key "status" and string value "ok".'),
    ("READY", "Reply with exactly: READY"),
    ("4", "What is 2+2? Reply with only the number."),
]
rows = []
for expected, prompt in cases:
    body = json.dumps(
        {
            "model": "google/gemma-4-31B-it",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 32,
        }
    ).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        body,
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        raw = json.load(response)
    text = raw["choices"][0]["message"]["content"].strip()
    usage = raw.get("usage", {})
    if expected == "json":
        try:
            cleaned = text.strip().removeprefix("```json").removesuffix("```").strip()
            passed = json.loads(cleaned).get("status") == "ok"
        except Exception:
            passed = False
    else:
        passed = text == expected
    rows.append(
        {
            "expected": expected,
            "text": text[:500],
            "pass": passed,
            "finite": isinstance(text, str),
            "usage": usage,
        }
    )
value = {"schema_version": 1, "pass": all(row["pass"] for row in rows), "rows": rows}
pathlib.Path(sys.argv[2]).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
raise SystemExit(0 if value["pass"] else 20)
PY
smoke_rc=$?
set -e
if [[ "$smoke_rc" -eq 20 ]]; then
  atomic_terminal semantic_reject candidate_failed_cheap_semantic_smoke
  exit 0
elif [[ "$smoke_rc" -ne 0 ]]; then
  fail semantic_smoke_harness_failed
fi

set +e
python3 - \
  "$artifacts/graph-boundary/SOURCE_BINDING.json" \
  "$artifacts/graph-boundary/STATE.json" \
  "$artifacts/graph-boundary/head.jsonl" \
  "$artifacts/GRAPH_BOUNDARY_DECISION.json" <<'PY'
import json
import pathlib
import sys

source = json.load(open(sys.argv[1]))
state = json.load(open(sys.argv[2]))
heads = [
    json.loads(line)
    for line in pathlib.Path(sys.argv[3]).read_text().splitlines()
    if line.strip()
]
anchors = source.get("source_anchors", {})
runtime_hashes = source.get("runtime_source", {})
expected = source.get("expected_source", {})
hash_pass = all(
    runtime_hashes.get(name, {}).get("sha256") == digest
    for name, digest in expected.items()
)
head_rows = [
    row
    for row in heads
    if row.get("event") == "e4m3_head" and 1 <= int(row.get("m", 0)) <= 32
]
post_graph = any(
    row.get("post_graph_replay") is True
    and row.get("stream_capturing") is False
    and row.get("latest_completed_graph_replay")
    and row.get("candidate_symbol")
    == "sglang.srt.layers.quantization.fp8_utils.apply_fp8_linear"
    and row.get("candidate_output", {}).get("dtype") == "torch.bfloat16"
    and row.get("embedding", {}).get("dtype") == "torch.bfloat16"
    and row.get("candidate_weight", {}).get("dtype") == "torch.float8_e4m3fn"
    and float(row.get("final_logit_softcapping")) == 30.0
    and row.get("bf16_head_fallback") is False
    for row in head_rows
)
value = {
    "schema_version": 1,
    "pass": bool(
        all(anchors.values())
        and hash_pass
        and state.get("successful_capture_batch_sizes")
        and state.get("replay_count_lower_bound", 0) > 0
        and state.get("candidate_head_count_lower_bound", 0) > 0
        and state.get("bf16_head_fallback_count") == 0
        and post_graph
    ),
    "source_anchor_pass": all(anchors.values()),
    "runtime_hash_pass": hash_pass,
    "model_forward_capture_batch_sizes": state.get(
        "successful_capture_batch_sizes", []
    ),
    "model_forward_replay_count_lower_bound": state.get(
        "replay_count_lower_bound", 0
    ),
    "observed_head_m": state.get("observed_head_m", []),
    "bf16_head_fallback_count": state.get("bf16_head_fallback_count"),
    "post_graph_e4m3_head_pass": post_graph,
    "head_rows": head_rows,
    "sampling_and_token_path": "unchanged pinned sampler and model-runner sources",
    "logits_softcap": 30.0,
}
pathlib.Path(sys.argv[4]).write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n"
)
raise SystemExit(0 if value["pass"] else 20)
PY
graph_rc=$?
set -e
if [[ "$graph_rc" -eq 20 ]]; then
  atomic_terminal graph_boundary_reject required_post_graph_e4m3_path_not_proven
  exit 0
elif [[ "$graph_rc" -ne 0 ]]; then
  fail graph_boundary_harness_failed
fi

# Persisted producer evidence is complete. The following marker immediately
# precedes the one and only previously unstarted c32 endpoint invocation.
set_state endpoint_science_started
sudo docker exec "$container" \
  python3 /work/fp8-graph-endpoint/input/binding/fp8_qkv_paired_runner.py \
    --output /work/fp8-graph-endpoint/artifacts/endpoint \
    --arm fp8_tied_head_e4m3_graph_bound_ring --concurrency 32 \
    >"$artifacts/endpoint.runner.stdout" \
    2>"$artifacts/endpoint.runner.stderr" \
  || fail endpoint_runner_failed
set_state endpoint_request_accepted

set +e
python3 - \
  "$artifacts/endpoint/TERMINAL.json" \
  "$artifacts/SEMANTIC_SMOKE.json" \
  "$artifacts/GRAPH_BOUNDARY_DECISION.json" \
  "$input/binding/settled-COMPONENT_RESULT.json" \
  "$artifacts/ENDPOINT_RESULT.json" <<'PY'
import json
import math
import pathlib
import sys

candidate, smoke, graph, component = [json.load(open(path)) for path in sys.argv[1:5]]
comparator = 0.6556567115001144
latency = float(candidate["service_seconds_per_request"])
cache = candidate.get("cache", {})
accounting = (
    cache.get("cached_prompt_tokens_delta") == 17120
    and cache.get("uncached_prompt_tokens_delta") == 117728
)
rows = (
    candidate.get("complete_requests") == 32
    and len(candidate.get("rows", [])) == 32
    and all(
        row.get("error") is None
        and row.get("text_finite") is True
        and row.get("prompt_tokens") == 4214
        and row.get("completion_tokens") == 358
        for row in candidate.get("rows", [])
    )
)
valid = bool(
    candidate.get("pass") is True
    and accounting
    and rows
    and smoke.get("pass") is True
    and graph.get("pass") is True
    and math.isfinite(latency)
)
value = {
    "schema_version": 1,
    "status": "terminal",
    "classification": (
        "endpoint_positive"
        if valid and latency < comparator
        else "endpoint_nonpositive"
        if valid
        else "endpoint_invalid"
    ),
    "pass": valid and latency < comparator,
    "valid_endpoint": valid,
    "candidate_seconds_per_request": latency,
    "qualified_ring_comparator_seconds_per_request": comparator,
    "reduction_fraction": 1 - latency / comparator,
    "economic_ceiling_seconds_per_request": 0.6381105231,
    "ceiling_pass": valid and latency <= 0.6381105231,
    "accounting_pass": accounting,
    "finite_32_rows_pass": rows,
    "component_replayed": False,
    "settled_component": component,
    "graph_boundary": graph,
    "semantic_smoke": smoke,
    "candidate": candidate,
    "quality_suite_required": True,
    "quality_claim_authorized": False,
}
pathlib.Path(sys.argv[5]).write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n"
)
raise SystemExit(0 if valid else 20)
PY
endpoint_rc=$?
set -e
if [[ "$endpoint_rc" -eq 20 ]]; then
  atomic_terminal endpoint_invalid endpoint_contract_failed
  exit 0
fi
atomic_terminal completed scientific_terminal_persisted
