#!/usr/bin/env bash
set -Eeuo pipefail

OUT="${OUT:-/workspace/campaign-100-phase-b}"
PUBLIC="${PUBLIC:-/workspace/public}"
MODEL="${MODEL:-/workspace/model-bf16}"
WORKLOAD="${WORKLOAD:-/workspace/frozen-workloads}"
QUALITY="${QUALITY:-/workspace/frozen-quality}"
CONFIGURATION="${CONFIGURATION:-stock_no_cache_fcfs}"
SERVER_EXTRA_ARGS_B64="${SERVER_EXTRA_ARGS_B64:-}"
export CONFIGURATION SERVER_EXTRA_ARGS_B64
export OUT PUBLIC MODEL WORKLOAD QUALITY
export HF_HUB_DISABLE_XET=1
STARTUP_TIMEOUT_SECONDS=900
PROFILE_TIMEOUT_SECONDS=600
TELEMETRY_CADENCE_SECONDS=1
MODEL_REVISION=75fce703a93da3705c4cf8d3caadbac1d1072c78
SOURCE_REVISION=f63458b5beaceabbd9d749b9fc956370e1b649e6
IMAGE_DIGEST=sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af
WORKLOAD_SHA256=f47c7af5e53483524010d06a93313b29f1a10c08f7df4bf18638349b4767193a
TOKENIZER_BINDINGS_SHA256=ccbe405b3abcef13f95dc7882f3ab21f8fa3443a97a340f9e8c4070682ecb14c
QUALITY_SHA256=152548d51fba8e8ff5e8f1e665c5af166fb6d97cdf3010723042112855964668
EXPERIMENT_SPEC_SHA256="${EXPERIMENT_SPEC_SHA256:?missing experiment specification identity}"
WORKLOAD_ARCHIVE_B64="${WORKLOAD_ARCHIVE_B64:-}"
QUALITY_ARCHIVE_B64="${QUALITY_ARCHIVE_B64:-}"
ARTIFACT_BUILDER_B64="${ARTIFACT_BUILDER_B64:-}"
WORKLOAD_ARCHIVE_PATH="${WORKLOAD_ARCHIVE_PATH:-}"
QUALITY_ARCHIVE_PATH="${QUALITY_ARCHIVE_PATH:-}"
ARTIFACT_BUILDER_PATH="${ARTIFACT_BUILDER_PATH:-}"
SERVE_ARTIFACT="${SERVE_ARTIFACT:-1}"
CAMPAIGN_DEADLINE_EPOCH="${CAMPAIGN_DEADLINE_EPOCH:?missing campaign deadline}"

HTTP_PID=
SERVER_PID=
TELEMETRY_PID=
SCHEDULER_PID=
DCGM_PID=

mkdir -p "$OUT" "$PUBLIC" "$WORKLOAD" "$QUALITY" "$OUT/plans" "$OUT/profiles"

phase() {
  python3 - "$1" "$2" <<'PY' >> "$OUT/phases.jsonl"
import datetime
import json
import sys

print(json.dumps({"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "phase": sys.argv[1], "state": sys.argv[2]}, separators=(",", ":")))
PY
}

stop_process() {
  local pid=${1:-}
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}

package_artifact() {
  rm -f "$OUT/manifest.json"
  if [ -n "$ARTIFACT_BUILDER_PATH" ]; then
    cp "$ARTIFACT_BUILDER_PATH" /tmp/artifact_builder.py
  else
    test -n "$ARTIFACT_BUILDER_B64"
    printf '%s' "$ARTIFACT_BUILDER_B64" | base64 -d > /tmp/artifact_builder.py
  fi
  cp /tmp/artifact_builder.py "$OUT/artifact-builder.py"
  python3 /tmp/artifact_builder.py manifest --bundle-root "$OUT" --output "$OUT/manifest.json"
  test -s "$OUT/manifest.json" || return 1
  tar -C /workspace -czf "$PUBLIC/phase-b-control.tar.gz.tmp" "$(basename "$OUT")"
  mv "$PUBLIC/phase-b-control.tar.gz.tmp" "$PUBLIC/phase-b-control.tar.gz"
  sha256sum "$PUBLIC/phase-b-control.tar.gz" > "$PUBLIC/phase-b-control.tar.gz.sha256"
}

finish() {
  local rc=$?
  set +e
  phase teardown begin
  stop_process "$SCHEDULER_PID"
  stop_process "$SERVER_PID"
  stop_process "$DCGM_PID"
  stop_process "$TELEMETRY_PID"
  nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1
  phase teardown complete
  package_artifact || rc=1
  if [ "$rc" -eq 0 ]; then
    printf 'READY\n' > "$PUBLIC/STATUS"
  else
    printf 'FAILED\n' > "$PUBLIC/STATUS"
  fi
  printf '%s\n' "$rc" > "$PUBLIC/EXIT_CODE"
  if [ "$SERVE_ARTIFACT" -eq 1 ]; then
    wait "$HTTP_PID"
  fi
}

trap finish EXIT
printf 'BOOTSTRAP\n' > "$PUBLIC/STATUS"
if [ "$SERVE_ARTIFACT" -eq 1 ]; then
  python3 -m http.server 8000 --bind 0.0.0.0 --directory "$PUBLIC" > "$PUBLIC/http-server.stdout.log" 2> "$PUBLIC/http-server.stderr.log" &
  HTTP_PID=$!
fi

phase bootstrap begin
if [ -n "$WORKLOAD_ARCHIVE_PATH" ]; then
  cp "$WORKLOAD_ARCHIVE_PATH" /tmp/frozen-workloads.tar.gz
else
  test -n "$WORKLOAD_ARCHIVE_B64"
  printf '%s' "$WORKLOAD_ARCHIVE_B64" | base64 -d > /tmp/frozen-workloads.tar.gz
fi
tar -xzf /tmp/frozen-workloads.tar.gz -C "$WORKLOAD"
test "$(python3 "$WORKLOAD/validate_bundle.py")" = "$WORKLOAD_SHA256"
test "$(sha256sum "$WORKLOAD/TOKENIZER_BINDINGS.json" | awk '{print $1}')" = "$TOKENIZER_BINDINGS_SHA256"
if [ -n "$QUALITY_ARCHIVE_PATH" ]; then
  cp "$QUALITY_ARCHIVE_PATH" /tmp/frozen-quality.tar.gz
else
  test -n "$QUALITY_ARCHIVE_B64"
  printf '%s' "$QUALITY_ARCHIVE_B64" | base64 -d > /tmp/frozen-quality.tar.gz
fi
tar -xzf /tmp/frozen-quality.tar.gz -C "$QUALITY"
test "$(python3 "$QUALITY/validate_quality.py")" = "$QUALITY_SHA256"
python3 - <<'PY' > "$OUT/contract-identities.json"
import json
import os

print(json.dumps({
    "experiment_spec_sha256": os.environ["EXPERIMENT_SPEC_SHA256"],
    "workload_sha256": "f47c7af5e53483524010d06a93313b29f1a10c08f7df4bf18638349b4767193a",
    "tokenizer_bindings_sha256": "ccbe405b3abcef13f95dc7882f3ab21f8fa3443a97a340f9e8c4070682ecb14c",
    "quality_sha256": "152548d51fba8e8ff5e8f1e665c5af166fb6d97cdf3010723042112855964668",
    "runtime_source_revision": "f63458b5beaceabbd9d749b9fc956370e1b649e6",
    "runtime_image_digest": "sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af",
    "model": "zai-org/GLM-4.7-Flash",
    "model_revision": "75fce703a93da3705c4cf8d3caadbac1d1072c78",
    "configuration": os.environ.get("CONFIGURATION", "stock_no_cache_fcfs"),
    "mtp": "enabled" if os.environ.get("SERVER_EXTRA_ARGS_B64") else "disabled",
    "profile_sequence": ["fixed_8k_1k_c1", "fixed_8k_1k_c8"],
    "agent_tool_call_itl_claim": "not_permitted_tool_parser_buffers_tokens",
    "semantic_quality_measurement": "separate_stock_chat_capture",
    "headline_c32_admissible": False,
    "service_contract": {"p95_ttft_ms": 10000, "p95_inter_token_ms": 100, "request_success_fraction": 0.99, "silent_truncation": False},
}, indent=2))
PY
uname -a > "$OUT/uname.txt"
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt" 2>&1
python3 -m pip freeze > "$OUT/pip-freeze.txt"
phase bootstrap complete

phase telemetry begin
printf '%s\n' 'timestamp,uuid,name,pstate,gpu_utilization_percent,memory_utilization_percent,memory_used_mib,memory_total_mib,power_draw_w,power_limit_w,temperature_c,sm_clock_mhz,memory_clock_mhz' > "$OUT/telemetry.csv"
(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep "$TELEMETRY_CADENCE_SECONDS"
  done
) >> "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" &
TELEMETRY_PID=$!
if command -v dcgmi >/dev/null; then
  timeout --signal=TERM 7000 dcgmi dmon -e 1002,1003,1004,1005,1009,1010,1011,1012 -d 1000 > "$OUT/dcgm-dmon.csv" 2> "$OUT/dcgm-dmon.stderr.log" &
  DCGM_PID=$!
else
  printf 'dcgmi unavailable\n' > "$OUT/dcgm-unavailable.txt"
fi
phase telemetry active

phase native_import begin
timeout --signal=TERM 120 python3 - <<'PY' > "$OUT/native-import.json"
import hashlib
import inspect
import json
from pathlib import Path

import sglang
import torch
import transformers
from sglang.srt.models.glm4_moe_lite import Glm4MoeLiteForCausalLM

source = Path(inspect.getfile(Glm4MoeLiteForCausalLM))
print(json.dumps({"class": Glm4MoeLiteForCausalLM.__name__, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "sglang": sglang.__version__, "torch": torch.__version__, "cuda": torch.version.cuda, "transformers": transformers.__version__}, indent=2))
PY
phase native_import complete

phase model_download begin
if [ ! -s "$MODEL/config.json" ] || [ ! -s "$MODEL/model.safetensors.index.json" ]; then
timeout --signal=TERM 1200 python3 - <<'PY' > "$OUT/model-download.log" 2>&1
import os
from huggingface_hub import HfApi, snapshot_download

revision = "75fce703a93da3705c4cf8d3caadbac1d1072c78"
info = HfApi().model_info("zai-org/GLM-4.7-Flash", revision=revision)
if info.sha != revision:
    raise SystemExit(f"revision mismatch: {info.sha}")
print("resolved_revision=" + info.sha)
print(snapshot_download("zai-org/GLM-4.7-Flash", revision=revision, local_dir=os.environ["MODEL"]))
PY
else
  printf 'reused exact model directory from prior same-host arm\n' > "$OUT/model-download.log"
fi
sha256sum "$MODEL/config.json" "$MODEL/model.safetensors.index.json" > "$OUT/model-hashes.sha256"
grep -q '^dc9b97c7c9bed726a2e6939da4234d5c43abb3edec8812068c9a1af1dbc13acb ' "$OUT/model-hashes.sha256"
grep -q '^91e6e95ca21700f50904a680c8c4212f5aa16dc7c10a013f01c906957c889791 ' "$OUT/model-hashes.sha256"
sha256sum "$MODEL/tokenizer.json" "$MODEL/tokenizer_config.json" "$MODEL/chat_template.jinja" > "$OUT/tokenizer-source-hashes.sha256"
grep -q '^19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d ' "$OUT/tokenizer-source-hashes.sha256"
grep -q '^31a173e2797ddc8b72ac996803513e627fc28d7aad02cfcce321a431d865c86d ' "$OUT/tokenizer-source-hashes.sha256"
grep -q '^d63ad536c3c81880043e22ec7fd08db42b4d8fb7c89c7138bc562bfa25281375 ' "$OUT/tokenizer-source-hashes.sha256"
du -sb "$MODEL" > "$OUT/model-size.txt"
phase model_download complete

phase plan_materialization begin
python3 - <<'PY'
import hashlib
import json
import os
import struct
from pathlib import Path

from transformers import AutoTokenizer
from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
from sglang.srt.entrypoints.openai.serving_chat import (
    normalize_assistant_tool_call_arguments,
    normalize_tool_content,
)
from sglang.srt.parser.jinja_template_utils import process_content_for_template_format

WORKLOAD = Path(os.environ["WORKLOAD"])
OUT = Path(os.environ["OUT"])
BUNDLE_SHA = "f47c7af5e53483524010d06a93313b29f1a10c08f7df4bf18638349b4767193a"
READ_FILE_TOOL = {
    "name": "read_file",
    "description": "Read one UTF-8 file now",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
}

tokenizer = AutoTokenizer.from_pretrained(os.environ["MODEL"])
records = {
    row["fixture_id"]: row
    for name in ("development.jsonl", "holdout.jsonl")
    for row in map(json.loads, (WORKLOAD / name).read_text().splitlines())
}
bindings_file = json.loads((WORKLOAD / "TOKENIZER_BINDINGS.json").read_text())
bindings = {row["fixture_id"]: row for row in bindings_file["bindings"]}
profiles = {row["profile_id"]: row for row in json.loads((WORKLOAD / "REPLAY_SCHEDULE.json").read_text())["profiles"]}

def token_hash(ids):
    return hashlib.sha256(b"".join(struct.pack("<I", value) for value in ids)).hexdigest()

def rendered_ids(messages, tools=None):
    request = ChatCompletionRequest(
        messages=messages,
        tools=[{"type": "function", "function": tool} for tool in tools] if tools else None,
        model="zai-org/GLM-4.7-Flash",
        max_tokens=1,
    )
    normalized = [message.model_dump() for message in request.messages]
    for message in normalized:
        normalize_assistant_tool_call_arguments(message)
    processed = []
    for message in normalized:
        if message.get("content") is None:
            message["content"] = ""
        row = process_content_for_template_format(message, "string", [], [], [], [])
        row["content"] = normalize_tool_content(row["role"], row.get("content"))
        processed.append(row)
    transport_tools = [tool.model_dump() for tool in request.tools] if request.tools else None
    rendered = tokenizer.apply_chat_template(
        processed,
        tools=transport_tools,
        tokenize=False,
        add_generation_prompt=True,
        return_dict=False,
    )
    return tokenizer.encode(rendered, add_special_tokens=False)

def fixed_prompt():
    atom = tokenizer.encode(" code", add_special_tokens=False)
    if len(atom) != 1:
        raise SystemExit("fixed workload has no stable one-token atom")
    prompt = tokenizer.decode(atom * 8192)
    if len(tokenizer.encode(prompt, add_special_tokens=False)) != 8192:
        raise SystemExit("could not materialize an exact 8192-token completion prompt")
    return prompt

def append_material():
    fixture = records["development_append_1"]
    messages = [{"role": "system", "content": fixture["session"]["system"]}]
    for turn in fixture["session"]["turns"]:
        if "tool_call" in turn:
            messages.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": turn["tool_call"]["name"], "arguments": turn["tool_call"]["arguments"]}}]})
        else:
            messages.append({"role": turn["role"], "content": turn["content"]})
    binding = bindings[fixture["fixture_id"]]
    ids = rendered_ids(messages, [READ_FILE_TOOL])
    if len(ids) != binding["input_tokens"] or token_hash(ids) != binding["token_ids_u32le_sha256"]:
        raise SystemExit("append tokenizer binding mismatch")
    return fixture, messages, [READ_FILE_TOOL], binding["server_reported_input_tokens"]

def prefix_material(index):
    fixture = records["development_prefix_1"]
    request = fixture["requests"][index]
    messages = [{"role": "system", "content": fixture["shared_prefix"]["system"]}, {"role": "user", "content": request["user"]}]
    binding = bindings[fixture["fixture_id"]]["requests"][index]
    tools = fixture["shared_prefix"]["tools"]
    ids = rendered_ids(messages, tools)
    if len(ids) != binding["input_tokens"] or token_hash(ids) != binding["token_ids_u32le_sha256"]:
        raise SystemExit(f"prefix tokenizer binding mismatch: {index}")
    return fixture, messages, tools, binding["server_reported_input_tokens"], index

fixed_fixture = records["development_fixed_1"]
fixed = (fixed_fixture, fixed_prompt(), None, 8192)

def request(material, request_id, offset=0):
    fixture, content, tools, expected, *request_index = material
    row = {
        "schema_version": 1,
        "request_id": request_id,
        "fixture_id": fixture["fixture_id"],
        "max_output_tokens": fixture.get("max_output_tokens", fixture.get("requests", [{}])[request_index[0] if request_index else 0].get("max_output_tokens")),
        "expected_input_tokens": expected,
        "scheduled_offset_ms": offset,
    }
    if tools is None:
        row["prompt"] = content
    else:
        row["messages"] = content
        row["tools"] = tools
    if request_index:
        row["request_index"] = request_index[0]
    return row

def repeat(material, count, prefix):
    return [request(material, f"{prefix}-{index:03d}") for index in range(count)]

blueprints = {
    "fixed_8k_1k_c1": {"warmup": [fixed], "measured": [fixed] * 4},
    "fixed_8k_1k_c8": {"warmup": [fixed] * 4, "measured": [fixed] * 16},
}
identities = []
for profile_id in ("fixed_8k_1k_c1", "fixed_8k_1k_c8"):
    profile = profiles[profile_id]
    blueprint = blueprints[profile_id]
    configuration = __import__("os").environ.get("CONFIGURATION", "stock_no_cache_fcfs")
    warmup = [request(material, f"{configuration}-{profile_id}-warmup-{index:03d}") for index, material in enumerate(blueprint["warmup"])]
    measured = [request(material, f"{configuration}-{profile_id}-measured-{index:03d}") for index, material in enumerate(blueprint["measured"])]
    if len(warmup) != profile["warmup"]["request_count"] or len(measured) != profile["request_count"]:
        raise SystemExit(f"materialized request cardinality mismatch: {profile_id}")
    plan = {"schema_version": 1, "bundle_sha256": BUNDLE_SHA, "profile_id": profile_id, "cache_mode": profile["cache"]["prefix_cache"], "warmup_requests": warmup, "requests": measured}
    payload = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    path = OUT / "plans" / f"{profile_id}.json"
    path.write_bytes(payload)
    identities.append({"profile_id": profile_id, "plan_sha256": hashlib.sha256(payload).hexdigest(), "warmup_requests": len(warmup), "measured_requests": len(measured), "max_concurrency": profile["max_concurrency"], "cache_mode": profile["cache"]["prefix_cache"]})
(OUT / "materialized-plan-identities.json").write_text(json.dumps(identities, indent=2) + "\n")
PY
phase plan_materialization complete

start_scheduler_sampler() {
  (
    while kill -0 "$SERVER_PID" 2>/dev/null; do
      python3 - <<'PY' >> "$OUT/scheduler-samples.jsonl"
import datetime
import hashlib
import json
import os
import urllib.request

try:
    payload = urllib.request.urlopen("http://127.0.0.1:30000/metrics", timeout=5).read()
    print(json.dumps({"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "configuration": os.environ.get("CONFIGURATION", "stock_no_cache_fcfs"), "metrics_sha256": hashlib.sha256(payload).hexdigest(), "metrics": payload.decode(errors="replace")}, separators=(",", ":")))
except Exception as error:
    print(json.dumps({"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "configuration": os.environ.get("CONFIGURATION", "stock_no_cache_fcfs"), "error": repr(error)}, separators=(",", ":")))
PY
      sleep 1
    done
  ) &
  SCHEDULER_PID=$!
}

phase stock_server begin
SERVER_EXTRA_ARGS=()
if [ -n "$SERVER_EXTRA_ARGS_B64" ]; then
  mapfile -t SERVER_EXTRA_ARGS < <(printf '%s' "$SERVER_EXTRA_ARGS_B64" | base64 -d)
fi
CMD=(
  python3 -m sglang.launch_server
  --model-path "$MODEL"
  --served-model-name zai-org/GLM-4.7-Flash
  --model-impl sglang
  --host 127.0.0.1
  --port 30000
  --context-length 32768
  --max-running-requests 32
  --mem-fraction-static 0.90
  --chunked-prefill-size 8192
  --tool-call-parser glm47
  --reasoning-parser glm45
  --stream-interval 1
  --disable-radix-cache
  --schedule-policy fcfs
  --enable-metrics
  --enable-request-time-stats-logging
  --random-seed 1234
  "${SERVER_EXTRA_ARGS[@]}"
)
printf '%q ' "${CMD[@]}" > "$OUT/stock-server-command.txt"
printf '\n' >> "$OUT/stock-server-command.txt"
server_started=$(date +%s.%N)
"${CMD[@]}" > "$OUT/stock-server.stdout.log" 2> "$OUT/stock-server.stderr.log" &
SERVER_PID=$!
deadline=$(( $(date +%s) + STARTUP_TIMEOUT_SECONDS ))
healthy=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    wait "$SERVER_PID"
    exit $?
  fi
  if curl -fsS http://127.0.0.1:30000/health >/dev/null; then
    healthy=1
    break
  fi
  sleep 2
done
test "$healthy" -eq 1
server_ready=$(date +%s.%N)
python3 - "$server_started" "$server_ready" <<'PY' > "$OUT/startup-timings.jsonl"
import json
import sys

print(json.dumps({"configuration": "stock_no_cache_fcfs", "server_process_started_epoch": float(sys.argv[1]), "server_ready_epoch": float(sys.argv[2]), "server_ready_seconds": float(sys.argv[2]) - float(sys.argv[1])}, separators=(",", ":")))
PY
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/stock-metrics-before.txt"
start_scheduler_sampler
phase stock_server complete

convert_profile() {
  local profile=$1
  python3 - "$profile" <<'PY'
import json
import math
import os
import sys
from pathlib import Path

profile = sys.argv[1]
root = Path(os.environ["OUT"])
source = root / "profiles" / f"{profile}-runner-outcomes.jsonl"
if not source.is_file():
    raise SystemExit(f"runner did not produce typed outcomes: {profile}")
rows = [json.loads(line) for line in source.read_text().splitlines()]

def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    return values[min(len(values) - 1, max(0, math.ceil(len(values) * fraction) - 1))]

converted = []
for row in rows:
    success = row["status"] == "success"
    detected_truncation = row["truncation"]["detected"] is True
    request_itl = percentile(row["latency_ms"]["itl"], 0.95) if success else None
    if success and request_itl is None:
        request_itl = 0.0
    has_error = not success or detected_truncation
    eligible = success and not detected_truncation
    ttft = row["latency_ms"]["ttft"]
    compliant = eligible and ttft <= 10000 and request_itl <= 100
    tokens = row["tokens"]
    converted.append({
        "request_id": f"{__import__('os').environ.get('CONFIGURATION', 'stock_no_cache_fcfs')}:{profile}:{row['repetition']}:{row['request_id']}",
        "completed": success,
        "slo_eligible": eligible,
        "slo_compliant": compliant,
        "error": has_error,
        "silent_truncation": False,
        "input_tokens": tokens["input"] if isinstance(tokens["input"], int) else 0,
        "output_tokens": tokens["output"] if isinstance(tokens["output"], int) else 0,
        "ttft_ms": ttft,
        "inter_token_latency_ms": request_itl,
        "end_to_end_ms": row["latency_ms"]["end_to_end"],
    })
with (root / "request-outcomes.jsonl").open("a") as handle:
    for row in converted:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
PY
}

summarize_profile() {
  local profile=$1
  local runner_started=$2
  local runner_ended=$3
  python3 - "$profile" "$runner_started" "$runner_ended" <<'PY'
import json
import math
import os
import sys
from pathlib import Path

profile, started, ended = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
root = Path(os.environ["OUT"])
rows = [json.loads(line) for line in (root / "profiles" / f"{profile}-runner-outcomes.jsonl").read_text().splitlines()]
expected = {"fixed_8k_1k_c1": 4, "fixed_8k_1k_c8": 16}[profile]
if len(rows) != expected:
    raise SystemExit(f"profile cardinality mismatch: {profile}")

def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, math.ceil(len(values) * fraction) - 1))] if values else None

successful = [row for row in rows if row["status"] == "success" and row["truncation"]["detected"] is False]
ttft = [row["latency_ms"]["ttft"] for row in successful]
itl = [value for row in successful for value in row["latency_ms"]["itl"]]
success_fraction = len(successful) / len(rows)
ttft_p95 = percentile(ttft, 0.95)
itl_p95 = percentile(itl, 0.95)
input_tokens = sum(row["tokens"]["input"] or 0 for row in rows)
output_tokens = sum(row["tokens"]["output"] or 0 for row in rows)
wall = ended - started
summary = {
    "profile_id": profile,
    "requests": len(rows),
    "success_fraction": success_fraction,
    "errors": len(rows) - len(successful),
    "detected_truncations": sum(row["truncation"]["detected"] is True for row in rows),
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "conservative_runner_wall_seconds_including_warmup_and_cache_reset": wall,
    "input_tokens_per_second_conservative": input_tokens / wall,
    "output_tokens_per_second_conservative": output_tokens / wall,
    "ttft_ms": {"p50": percentile(ttft, 0.50), "p95": ttft_p95, "p99": percentile(ttft, 0.99)},
    "token_level_itl_ms": {"p50": percentile(itl, 0.50), "p95": itl_p95, "p99": percentile(itl, 0.99)},
    "frozen_slo_pass": success_fraction >= 0.99 and ttft_p95 is not None and itl_p95 is not None and ttft_p95 <= 10000 and itl_p95 <= 100,
}
(root / "profiles" / f"{profile}-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print("PASS" if summary["frozen_slo_pass"] else "FAIL")
PY
}

SEQUENCE_PASS=1
phase workload_sequence begin
for profile in fixed_8k_1k_c1 fixed_8k_1k_c8; do
  phase "$profile" begin
  runner_started=$(date +%s.%N)
  set +e
  timeout --signal=TERM 1800 python3 "$WORKLOAD/replay_api.py" \
    --bundle "$WORKLOAD" \
    --base-url http://127.0.0.1:30000 \
    --plan "$OUT/plans/$profile.json" \
    --output "$OUT/profiles/$profile-runner-outcomes.jsonl" \
    > "$OUT/profiles/$profile-runner.stdout.log" \
    2> "$OUT/profiles/$profile-runner.stderr.log"
  runner_rc=$?
  set -e
  runner_ended=$(date +%s.%N)
  convert_profile "$profile"
  profile_gate=$(summarize_profile "$profile" "$runner_started" "$runner_ended")
  python3 - "$profile" "$runner_rc" "$profile_gate" <<'PY' >> "$OUT/profile-gates.jsonl"
import json
import os
import sys
print(json.dumps({"profile_id": sys.argv[1], "runner_exit_code": int(sys.argv[2]), "slo_gate": sys.argv[3]}, separators=(",", ":")))
PY
  phase "$profile" complete
  if [ "$runner_rc" -ne 0 ] || [ "$profile_gate" != PASS ]; then
    SEQUENCE_PASS=0
    break
  fi
done
phase workload_sequence complete

QUALITY_PASS=0
if [ "$SEQUENCE_PASS" -eq 1 ]; then
  phase quality_capture begin
  set +e
  python3 "$QUALITY/run_pair.py" \
    --mode capture \
    --suite "$QUALITY" \
    --split development \
    --base-url http://127.0.0.1:30000 \
    --disable-thinking \
    --responses "$OUT/quality-${CONFIGURATION}-responses.jsonl" \
    --evidence "$OUT/quality-${CONFIGURATION}-evidence.json" \
    > "$OUT/quality-capture.stdout.log" \
    2> "$OUT/quality-capture.stderr.log"
  quality_capture_rc=$?
  if [ "$quality_capture_rc" -eq 0 ]; then
    python3 "$QUALITY/run_pair.py" \
      --mode score \
      --suite "$QUALITY" \
      --split development \
      --control-responses "$OUT/quality-${CONFIGURATION}-responses.jsonl" \
      --candidate-responses "$OUT/quality-${CONFIGURATION}-responses.jsonl" \
      --result-output "$OUT/quality-${CONFIGURATION}-self-score.json" \
      > "$OUT/quality-score.stdout.log" \
      2> "$OUT/quality-score.stderr.log"
    quality_score_rc=$?
  else
    quality_score_rc=1
  fi
  set -e
  if [ "$quality_capture_rc" -eq 0 ] && [ "$quality_score_rc" -eq 0 ]; then
    QUALITY_PASS=1
  fi
  python3 - "$quality_capture_rc" "$quality_score_rc" <<'PY' > "$OUT/quality-gate.json"
import json
import sys
print(json.dumps({"capture_exit_code": int(sys.argv[1]), "self_score_exit_code": int(sys.argv[2]), "pass": sys.argv[1] == "0" and sys.argv[2] == "0"}, indent=2))
PY
  phase quality_capture complete
fi

phase profiler begin
export SGLANG_TORCH_PROFILER_DIR="$OUT/profiler/$CONFIGURATION"
mkdir -p "$SGLANG_TORCH_PROFILER_DIR"
timeout --signal=TERM "$PROFILE_TIMEOUT_SECONDS" python3 -m sglang.benchmark.serving \
  --backend sglang \
  --base-url http://127.0.0.1:30000 \
  --model zai-org/GLM-4.7-Flash \
  --tokenizer "$MODEL" \
  --dataset-name random \
  --random-input-len 8192 \
  --random-output-len 128 \
  --random-range-ratio 1 \
  --num-prompts 1 \
  --max-concurrency 1 \
  --seed 20260713 \
  --disable-tqdm \
  --output-details \
  --profile \
  --profile-output-dir "$SGLANG_TORCH_PROFILER_DIR" \
  --output-file "$OUT/profiler-benchmark.json" \
  > "$OUT/profiler-benchmark.stdout.log" \
  2> "$OUT/profiler-benchmark.stderr.log"
find "$SGLANG_TORCH_PROFILER_DIR" -type f -size +0c -print > "$OUT/profiler-files.txt"
test -s "$OUT/profiler-files.txt"
phase profiler complete

stop_process "$SCHEDULER_PID"
SCHEDULER_PID=
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/stock-metrics-after.txt" || true
stop_process "$SERVER_PID"
SERVER_PID=

python3 - "$SEQUENCE_PASS" "$QUALITY_PASS" <<'PY' > "$OUT/allocation-result.json"
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["OUT"])
summaries = []
for profile in ("fixed_8k_1k_c1", "fixed_8k_1k_c8"):
    path = root / "profiles" / f"{profile}-summary.json"
    if path.is_file():
        summaries.append(json.loads(path.read_text()))
print(json.dumps({
    "configuration": __import__("os").environ.get("CONFIGURATION", "stock_no_cache_fcfs"),
    "sequence_pass": sys.argv[1] == "1",
    "quality_pass": sys.argv[2] == "1",
    "headline_c32_executed": False,
    "profiles": summaries,
    "agent_tool_call_itl_claim_permitted": False,
    "next_action": "evaluate_preregistered_mtp_on_fixed_slo_plus_separate_quality" if sys.argv[1] == "1" and sys.argv[2] == "1" else "stop_or_correct_measured_failure",
}, indent=2))
PY

phase packaging begin
phase packaging complete

if [ "$SEQUENCE_PASS" -ne 1 ] || [ "$QUALITY_PASS" -ne 1 ]; then
  exit 1
fi
