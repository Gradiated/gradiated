#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/campaign-100-observer
PUBLIC=/workspace/public-observer
PARTIAL=/workspace/campaign-100-observer-partial
MODEL=/workspace/model-awq
TOKENIZER=/input/tokenizer
SERVER=
TELEMETRY=
ACTIVE_SESSION=
CURRENT_PHASE=bootstrap
CURRENT_ARM=
CURRENT_MODE=

rm -rf "$OUT" "$PUBLIC" "$PARTIAL" "$PARTIAL.tmp"
mkdir -p "$OUT" "$PUBLIC" "$OUT/arms" "$OUT/arm-artifacts"

phase() {
  CURRENT_PHASE="$1"
  printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' \
    "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"
  refresh_partial_archive
}

record_server_status() {
  local arm="$1"
  local mode="$2"
  local state="$3"
  local exit_code="$4"
  local arm_dir="$OUT/arms/$arm"
  local pid="${SERVER:-null}"
  local row
  mkdir -p "$arm_dir"
  row="$(printf '{"timestamp":"%s","arm":"%s","mode":"%s","phase":"%s","pid":%s,"state":"%s","exit_code":%s}' \
    "$(date -u +%FT%TZ)" "$arm" "$mode" "$CURRENT_PHASE" "$pid" "$state" "$exit_code")"
  printf '%s\n' "$row" >> "$arm_dir/server-status-events.jsonl"
  printf '%s\n' "$row" > "$arm_dir/server-status.json.tmp"
  mv "$arm_dir/server-status.json.tmp" "$arm_dir/server-status.json"
}

refresh_partial_archive() {
  local staging="$PARTIAL.tmp"
  local arm_dir
  local name
  rm -rf "$staging"
  mkdir -p "$staging/arms"
  for name in phases.jsonl allocation-result.json nvidia-smi-final.txt host-bootstrap-launcher.sh host-bootstrap-launcher.json; do
    [ ! -f "$OUT/$name" ] || cp "$OUT/$name" "$staging/$name"
  done
  for arm_dir in "$OUT"/arms/*; do
    [ -d "$arm_dir" ] || continue
    mkdir -p "$staging/arms/$(basename "$arm_dir")"
    for name in probe.json server-command.txt server-status.json server-status-events.jsonl \
      server.stdout.log server.stderr.log health-attempts.jsonl health-curl.stderr.log \
      workload.json workload.stdout.log workload.stderr.log gate.json \
      scheduler-events.jsonl request-events.jsonl request-event.jsonl \
      raw-request.jsonl raw-events.jsonl dependency-events.jsonl dependency-manifest.json \
      metrics-before.txt metrics-after.txt nvidia-smi-loaded.txt telemetry.csv telemetry.stderr.log; do
      [ ! -f "$arm_dir/$name" ] || cp "$arm_dir/$name" "$staging/arms/$(basename "$arm_dir")/$name"
    done
  done
  for name in host-bootstrap-launcher.sh host-bootstrap-launcher.json; do
    [ ! -f "/input/$name" ] || cp "/input/$name" "$staging/$name"
  done
  printf '{"schema_version":1,"complete":false,"classification":"diagnostic_partial","timestamp":"%s","phase":"%s","arm":"%s","mode":"%s"}\n' \
    "$(date -u +%FT%TZ)" "$CURRENT_PHASE" "$CURRENT_ARM" "$CURRENT_MODE" > "$staging/partial-metadata.json"
  python3 - "$staging" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = []
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.name == "manifest.json":
        continue
    rows.append({
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    })
(root / "manifest.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
PY
  rm -rf "$PARTIAL"
  mv "$staging" "$PARTIAL"
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C /workspace -czf "$PUBLIC/observer-diagnostic-partial.tar.gz.tmp" "$(basename "$PARTIAL")"
  mv "$PUBLIC/observer-diagnostic-partial.tar.gz.tmp" "$PUBLIC/observer-diagnostic-partial.tar.gz"
  sha256sum "$PUBLIC/observer-diagnostic-partial.tar.gz" \
    > "$PUBLIC/observer-diagnostic-partial.tar.gz.sha256.tmp"
  mv "$PUBLIC/observer-diagnostic-partial.tar.gz.sha256.tmp" \
    "$PUBLIC/observer-diagnostic-partial.tar.gz.sha256"
}

stop_server() {
  local server_rc
  local terminated=0
  set +e
  if [ -n "$ACTIVE_SESSION" ]; then
    nsys shutdown --session="$ACTIVE_SESSION" --kill=sigterm >/dev/null 2>&1
  fi
  pkill -TERM -f 'vllm serve /workspace/model-awq' >/dev/null 2>&1
  [ -n "$SERVER" ] && kill -TERM "$SERVER" >/dev/null 2>&1
  if [ -n "$SERVER" ]; then
    for _ in $(seq 1 30); do
      if ! kill -0 "$SERVER" >/dev/null 2>&1 \
        || [ "$(awk '{print $3}' "/proc/$SERVER/stat" 2>/dev/null)" = Z ]; then
        terminated=1
        break
      fi
      sleep 1
    done
    if [ "$terminated" -ne 1 ]; then
      pkill -KILL -f 'vllm serve /workspace/model-awq' >/dev/null 2>&1
      kill -KILL "$SERVER" >/dev/null 2>&1
    fi
    wait "$SERVER" >/dev/null 2>&1
    server_rc=$?
    if kill -0 "$SERVER" >/dev/null 2>&1 || pgrep -f 'vllm serve /workspace/model-awq' >/dev/null 2>&1; then
      record_server_status "$CURRENT_ARM" "$CURRENT_MODE" stop_failed "$server_rc"
      refresh_partial_archive
      SERVER=
      ACTIVE_SESSION=
      set -e
      return 1
    fi
    record_server_status "$CURRENT_ARM" "$CURRENT_MODE" stopped_and_absent "$server_rc"
    refresh_partial_archive
  fi
  SERVER=
  ACTIVE_SESSION=
  set -e
}

package_session() {
  python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path("/workspace/campaign-100-observer")
rows = []
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.name == "manifest.json":
        continue
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    rows.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
(root / "manifest.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C /workspace -czf "$PUBLIC/observer-diagnostic.tar.gz.tmp" campaign-100-observer
  mv "$PUBLIC/observer-diagnostic.tar.gz.tmp" "$PUBLIC/observer-diagnostic.tar.gz"
  sha256sum "$PUBLIC/observer-diagnostic.tar.gz" > "$PUBLIC/observer-diagnostic.tar.gz.sha256"
}

finish() {
  rc=$?
  trap - EXIT
  set +e
  stop_server
  [ -n "$TELEMETRY" ] && kill -TERM "$TELEMETRY" >/dev/null 2>&1
  [ -n "$TELEMETRY" ] && wait "$TELEMETRY" >/dev/null 2>&1
  nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1
  if [ ! -s "$OUT/allocation-result.json" ]; then
    RC="$rc" FAILURE_PHASE="$CURRENT_PHASE" python3 - <<'PY'
import json
import os
from pathlib import Path
Path("/workspace/campaign-100-observer/allocation-result.json").write_text(json.dumps({
    "schema_version": 1,
    "bracket_complete": False,
    "classification": "invalid_harness_or_infrastructure",
    "error": {"return_code": int(os.environ["RC"]), "phase": os.environ["FAILURE_PHASE"]},
}, indent=2, sort_keys=True) + "\n")
PY
  fi
  refresh_partial_archive
  package_session
  exit "$rc"
}
trap finish EXIT

if [ "$(date +%s)" -ge "$SCIENCE_DEADLINE_EPOCH" ]; then
  echo "science deadline already exhausted" >&2
  exit 70
fi

phase environment_identity begin
uname -a > "$OUT/uname.txt"
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt" 2>&1
python3 -m pip freeze > "$OUT/pip-freeze.txt"
nsys --version > "$OUT/nsys-version.txt"
grep -F '2026.3.1.157' "$OUT/nsys-version.txt"
nsys status -e > "$OUT/nsys-status.txt" 2>&1
dpkg-query -W -f='${Package}=${Version}\n' nsight-systems-cli > "$OUT/nsys-package.txt"
python3 - <<'PY' > "$OUT/runtime-identity.json"
import json
import torch
import transformers
import vllm
print(json.dumps({
    "cuda": torch.version.cuda,
    "gpu": torch.cuda.get_device_name(),
    "gpu_capability": torch.cuda.get_device_capability(),
    "torch": torch.__version__,
    "transformers": transformers.__version__,
    "vllm": vllm.__version__,
}, indent=2, sort_keys=True))
PY
sha256sum /input/remote_observer_diagnostic.sh /input/observer_workload.py \
  /input/vllm_observer_patch.py /input/analyze_nsys_observer.py > "$OUT/harness-files.sha256"
phase environment_identity complete

(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" &
TELEMETRY=$!

phase retained_checkpoint_identity begin
MARKER="$MODEL/.campaign-integrity-v1"
MANIFEST_SHA="$(sha256sum "$MODEL_MANIFEST_PATH" | awk '{print $1}')"
METADATA_SHA="$(find "$MODEL" -maxdepth 1 -type f ! -name '.campaign-integrity-v1' -printf '%f %s %T@\n' | sort | sha256sum | awk '{print $1}')"
if [ -f "$MARKER" ] && grep -qx "manifest_sha256=$MANIFEST_SHA" "$MARKER" && grep -qx "metadata_sha256=$METADATA_SHA" "$MARKER"; then
  printf 'marker_reused=true\n' > "$OUT/model-manifest-verification.log"
else
  (cd "$MODEL" && sha256sum -c "$MODEL_MANIFEST_PATH") > "$OUT/model-manifest-verification.log" 2>&1
  printf 'manifest_sha256=%s\nmetadata_sha256=%s\n' "$MANIFEST_SHA" "$METADATA_SHA" > "$MARKER"
  printf 'marker_reused=false\n' >> "$OUT/model-manifest-verification.log"
fi
test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00004.safetensors' | wc -l)" -eq 4
test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00004.safetensors' -printf '%s\n' | awk '{s+=$1} END {printf "%.0f\n",s}')" = 20170199928
cp "$MODEL_MANIFEST_PATH" "$OUT/model-files.sha256"
cp "$MARKER" "$OUT/model-integrity-marker.txt"
sha256sum "$TOKENIZER/tokenizer.json" "$TOKENIZER/tokenizer_config.json" "$TOKENIZER/chat_template.jinja" > "$OUT/tokenizer-files.sha256"
phase retained_checkpoint_identity complete

CMD=(
  vllm serve "$MODEL"
  --tokenizer "$TOKENIZER"
  --served-model-name glm-4.7-flash-awq
  --host 127.0.0.1
  --port 30000
  --max-model-len 32768
  --max-num-seqs 8
  --max-num-batched-tokens 65536
  --gpu-memory-utilization 0.90
  --no-enable-prefix-caching
  --quantization compressed-tensors
  --dtype bfloat16
  --generation-config vllm
  --seed 1234
)

wait_healthy() {
  local arm="$1"
  local arm_dir="$OUT/arms/$arm"
  local healthy=0
  local attempt
  local curl_rc
  local http_status
  local server_rc
  for attempt in $(seq 1 180); do
    if ! kill -0 "$SERVER" 2>/dev/null; then
      printf '{"timestamp":"%s","arm":"%s","attempt":%s,"process_alive":false,"curl_return_code":null,"http_status":null}\n' \
        "$(date -u +%FT%TZ)" "$arm" "$attempt" >> "$arm_dir/health-attempts.jsonl"
      set +e
      wait "$SERVER"
      server_rc=$?
      set -e
      record_server_status "$arm" "$CURRENT_MODE" exited "$server_rc"
      refresh_partial_archive
      SERVER=
      return 1
    fi
    set +e
    http_status="$(curl -fsS -o /dev/null -w '%{http_code}' \
      http://127.0.0.1:30000/health 2>> "$arm_dir/health-curl.stderr.log")"
    curl_rc=$?
    set -e
    printf '{"timestamp":"%s","arm":"%s","attempt":%s,"process_alive":true,"curl_return_code":%s,"http_status":"%s"}\n' \
      "$(date -u +%FT%TZ)" "$arm" "$attempt" "$curl_rc" "$http_status" >> "$arm_dir/health-attempts.jsonl"
    if [ "$curl_rc" -eq 0 ]; then
      healthy=1
      break
    fi
    if [ $((attempt % 15)) -eq 0 ]; then
      refresh_partial_archive
    fi
    if [ "$(date +%s)" -ge "$SCIENCE_DEADLINE_EPOCH" ]; then
      break
    fi
    sleep 2
  done
  if [ "$healthy" -ne 1 ]; then
    record_server_status "$arm" "$CURRENT_MODE" readiness_failed null
    refresh_partial_archive
    echo "$arm server readiness failed" >&2
    return 1
  fi
  record_server_status "$arm" "$CURRENT_MODE" healthy null
  refresh_partial_archive
}

run_stock_startup_probe() {
  local arm_dir="$OUT/arms/STOCK_STARTUP"
  mkdir -p "$arm_dir"
  CURRENT_ARM="STOCK_STARTUP"
  CURRENT_MODE="stock-unpatched"
  phase stock_startup_probe begin
  if [ "$(date +%s)" -ge "$SCIENCE_DEADLINE_EPOCH" ]; then
    echo "science deadline reached before stock startup probe" >&2
    return 71
  fi
  printf '%q ' "${CMD[@]}" > "$arm_dir/server-command.txt"
  printf '\nmode=stock-unpatched\nscored_requests=0\n' >> "$arm_dir/server-command.txt"
  printf '{"schema_version":1,"excluded_from_measurement":true,"scored_requests":0,"purpose":"unpatched_startup_to_health","readiness_pass":null}\n' \
    > "$arm_dir/probe.json"
  unset GRAD_RESEARCH_SCHEDULER_EVENTS GRAD_RESEARCH_ARM_ID
  "${CMD[@]}" > "$arm_dir/server.stdout.log" 2> "$arm_dir/server.stderr.log" &
  SERVER=$!
  record_server_status "$CURRENT_ARM" "$CURRENT_MODE" running null
  refresh_partial_archive
  wait_healthy "$CURRENT_ARM"
  nvidia-smi -q > "$arm_dir/nvidia-smi-loaded.txt" 2>&1
  printf '{"schema_version":1,"excluded_from_measurement":true,"scored_requests":0,"purpose":"unpatched_startup_to_health","readiness_pass":true}\n' \
    > "$arm_dir/probe.json.tmp"
  mv "$arm_dir/probe.json.tmp" "$arm_dir/probe.json"
  refresh_partial_archive
  stop_server
  phase stock_startup_probe complete
}

run_stock_startup_probe

phase observer_patch begin
SCHEDULER_PATH="$(python3 - <<'PY'
import inspect
from vllm.v1.core.sched.scheduler import Scheduler
print(inspect.getsourcefile(Scheduler))
PY
)"
RUNNER_PATH="$(python3 - <<'PY'
import inspect
from vllm.v1.worker.gpu_model_runner import GPUModelRunner
print(inspect.getsourcefile(GPUModelRunner))
PY
)"
python3 /input/vllm_observer_patch.py \
  --scheduler "$SCHEDULER_PATH" \
  --gpu-model-runner "$RUNNER_PATH" \
  > "$OUT/observer-patch.json"
phase observer_patch complete

phase prompt_geometry begin
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("/input/tokenizer", local_files_only=True)
atom = tokenizer.encode(" code", add_special_tokens=False)
if len(atom) != 1:
    raise SystemExit("authoritative tokenizer has no one-token fixed atom")
prompt = tokenizer.decode(atom * 8192)
ids = tokenizer.encode(prompt, add_special_tokens=False)
if len(ids) != 8192:
    raise SystemExit("observer prompt is not exactly 8192 tokens")
Path("/workspace/campaign-100-observer/prompt.txt").write_text(prompt)
Path("/workspace/campaign-100-observer/prompt-identity.json").write_text(json.dumps({
    "atom_token_id": atom[0],
    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
    "prompt_tokens": len(ids),
}, indent=2, sort_keys=True) + "\n")
PY
phase prompt_geometry complete

archive_arm() {
  local arm="$1"
  local archive="$OUT/arm-artifacts/$arm-arm-artifact.tar.gz"
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C "$OUT/arms" -czf "$archive.tmp" "$arm"
  mv "$archive.tmp" "$archive"
  sha256sum "$archive" > "$OUT/arm-artifacts/$arm-arm-artifact.tar.gz.sha256"
}

run_warmup() {
  local arm="$1"
  local output="$OUT/arms/$arm/warmup.json"
  python3 - "$OUT/prompt.txt" "$arm" "$output" <<'PY'
import concurrent.futures
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, "/input")
from observer_workload import BASE_URL, MODEL, canonical, request_id

prompt = Path(sys.argv[1]).read_text()
arm = sys.argv[2]
output = Path(sys.argv[3])
barrier = threading.Barrier(8)

def one(index):
    correlation_id = request_id("observerwarmup", arm, index)
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "temperature": 0,
        "max_tokens": 16,
        "ignore_eos": True,
        "seed": 470146,
        "stream": False,
        "return_token_ids": True,
    }
    request = urllib.request.Request(
        BASE_URL + "/v1/completions",
        data=canonical(payload),
        headers={"Content-Type": "application/json", "X-Request-Id": correlation_id},
        method="POST",
    )
    barrier.wait(timeout=30)
    with urllib.request.urlopen(request, timeout=300) as response:
        value = json.loads(response.read())
    usage = value.get("usage") or {}
    choices = value.get("choices") or []
    row = {
        "request_id": correlation_id,
        "input_tokens": int(usage.get("prompt_tokens", -1)),
        "output_tokens": int(usage.get("completion_tokens", -1)),
        "finish_reason": choices[0].get("finish_reason") if choices else None,
    }
    if row["input_tokens"] != 8192 or row["output_tokens"] != 16 or row["finish_reason"] != "length":
        raise RuntimeError("excluded warmup geometry failed")
    return row

started_ns = time.monotonic_ns()
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    rows = [future.result() for future in concurrent.futures.as_completed([pool.submit(one, index) for index in range(8)])]
rows.sort(key=lambda row: row["request_id"])
output.write_text(json.dumps({
    "schema_version": 1,
    "arm_id": arm,
    "excluded_from_measurement": True,
    "concurrency": 8,
    "requests": 8,
    "prompt_tokens": 8192,
    "output_tokens": 16,
    "wall_seconds": (time.monotonic_ns() - started_ns) / 1_000_000_000,
    "rows": rows,
}, indent=2, sort_keys=True) + "\n")
PY
}

run_arm() {
  local arm="$1"
  local mode="$2"
  local sample_mode=none
  local context_switch_mode=none
  if [ "$mode" = nsys-full ]; then
    sample_mode=process-tree
    context_switch_mode=process-tree
  fi
  local arm_dir="$OUT/arms/$arm"
  local session="observer${arm}"
  mkdir -p "$arm_dir"
  CURRENT_ARM="$arm"
  CURRENT_MODE="$mode"
  phase "$arm" begin
  if [ "$(date +%s)" -ge "$SCIENCE_DEADLINE_EPOCH" ]; then
    echo "science deadline reached before $arm" >&2
    return 71
  fi
  printf '%q ' "${CMD[@]}" > "$arm_dir/server-command.txt"
  printf '\nmode=%s\nnsight_gpu_metrics=unsupported_on_l40s\n' "$mode" >> "$arm_dir/server-command.txt"
  export GRAD_RESEARCH_SCHEDULER_EVENTS="$arm_dir/scheduler-events.jsonl"
  export GRAD_RESEARCH_ARM_ID="$arm"
  if [[ "$mode" = nsys-* ]]; then
    ACTIVE_SESSION="$session"
    nsys launch --session-new="$session" \
      --trace=cuda,nvtx,osrt --cuda-graph-trace=node --cuda-event-trace=true \
      --sample="$sample_mode" --cpuctxsw="$context_switch_mode" \
      "${CMD[@]}" \
      > "$arm_dir/server.stdout.log" 2> "$arm_dir/server.stderr.log" &
    SERVER=$!
  else
    "${CMD[@]}" > "$arm_dir/server.stdout.log" 2> "$arm_dir/server.stderr.log" &
    SERVER=$!
  fi
  record_server_status "$arm" "$mode" running null
  refresh_partial_archive
  wait_healthy "$arm"
  nvidia-smi -q > "$arm_dir/nvidia-smi-loaded.txt" 2>&1
  run_warmup "$arm"
  curl -fsS http://127.0.0.1:30000/metrics > "$arm_dir/metrics-before.txt"
  if [[ "$mode" = nsys-* ]]; then
    nsys start --session="$session" --output="$arm_dir/trace" > "$arm_dir/nsys-start.log" 2>&1
  fi
  set +e
  python3 /input/observer_workload.py \
    --prompt-file "$OUT/prompt.txt" \
    --run-id observerdiag \
    --arm-id "$arm" \
    --output "$arm_dir/workload.json" \
    > "$arm_dir/workload.stdout.log" 2> "$arm_dir/workload.stderr.log"
  workload_rc=$?
  set -e
  curl -fsS http://127.0.0.1:30000/metrics > "$arm_dir/metrics-after.txt"
  if [[ "$mode" = nsys-* ]]; then
    nsys stop --session="$session" > "$arm_dir/nsys-stop.log" 2>&1
    ACTIVE_SESSION=
  fi
  stop_server
  if [[ "$mode" = nsys-* ]]; then
    test -s "$arm_dir/trace.nsys-rep"
    nsys export --force-overwrite=true --type=sqlite \
      --output="$arm_dir/trace.sqlite" "$arm_dir/trace.nsys-rep" \
      > "$arm_dir/nsys-export.stdout.log" 2> "$arm_dir/nsys-export.stderr.log"
    test -s "$arm_dir/trace.sqlite"
  fi
  test "$workload_rc" -eq 0
  python3 - "$arm_dir/workload.json" > "$arm_dir/gate.json" <<'PY'
import json
import sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text())
rows = value.get("rows", [])
geometry = bool(value.get("geometry_pass")) and len(rows) == 8
slo = geometry and all(row["ttft_ms"] <= 10000 and row["tpot_ms"] <= 100 for row in rows)
print(json.dumps({"geometry_pass": geometry, "slo_pass": slo, "ttft_ms_max": max(row["ttft_ms"] for row in rows), "tpot_ms_max": max(row["tpot_ms"] for row in rows)}, indent=2, sort_keys=True))
if not geometry or not slo:
    raise SystemExit(1)
PY
  archive_arm "$arm"
  phase "$arm" complete
}

# The exact same retained image, checkpoint, server flags, prompt, and request
# geometry are used. Only Nsight collection state changes across this bracket.
run_arm A1 off
run_arm B1 nsys-full
run_arm A2 off

python3 - <<'PY'
import json
import sys
from pathlib import Path
sys.path.insert(0, "/input")
from analyze_nsys_observer import observer_effect

root = Path("/workspace/campaign-100-observer/arms")
def metrics(name):
    value = json.loads((root / name / "workload.json").read_text())
    return {
        "throughput": value["output_tokens_per_second"],
        "median_latency_ms": value["end_to_end_ms"]["p50"],
        "tail_latency_ms": value["end_to_end_ms"]["p95"],
    }
result = observer_effect(metrics("A1"), metrics("B1"), metrics("A2"))
Path("/workspace/campaign-100-observer/observer-effect-primary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
PY

RUN_FALLBACK="$(python3 - <<'PY'
import json
import os
import time
from pathlib import Path
effect = json.loads(Path("/workspace/campaign-100-observer/observer-effect-primary.json").read_text())
remaining = max(0, int(os.environ["SCIENCE_DEADLINE_EPOCH"]) - int(time.time()))
remaining_cost = remaining / 3600 * float(os.environ["COMBINED_HOURLY_RATE_USD"])
admit = (not effect["pass"] and remaining >= int(os.environ["FALLBACK_MIN_SECONDS"]) and remaining_cost >= float(os.environ["FALLBACK_MIN_COST_USD"]))
Path("/workspace/campaign-100-observer/fallback-decision.json").write_text(json.dumps({
    "observer_gate_breached": not effect["pass"],
    "remaining_seconds": remaining,
    "remaining_cost_usd_derived": remaining_cost,
    "minimum_seconds": int(os.environ["FALLBACK_MIN_SECONDS"]),
    "minimum_cost_usd": float(os.environ["FALLBACK_MIN_COST_USD"]),
    "run_fallback": admit,
}, indent=2, sort_keys=True) + "\n")
print("true" if admit else "false")
PY
)"

if [ "$RUN_FALLBACK" = true ]; then
  run_arm B2 nsys-lite
  run_arm A3 off
  python3 - <<'PY'
import json
import sys
from pathlib import Path
sys.path.insert(0, "/input")
from analyze_nsys_observer import observer_effect
root = Path("/workspace/campaign-100-observer/arms")
def metrics(name):
    value = json.loads((root / name / "workload.json").read_text())
    return {"throughput": value["output_tokens_per_second"], "median_latency_ms": value["end_to_end_ms"]["p50"], "tail_latency_ms": value["end_to_end_ms"]["p95"]}
result = observer_effect(metrics("A2"), metrics("B2"), metrics("A3"))
Path("/workspace/campaign-100-observer/observer-effect-fallback.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
PY
fi

phase result begin
python3 - <<'PY'
import json
import os
from pathlib import Path
root = Path("/workspace/campaign-100-observer")
primary = json.loads((root / "observer-effect-primary.json").read_text())
fallback_decision = json.loads((root / "fallback-decision.json").read_text())
fallback_path = root / "observer-effect-fallback.json"
fallback = json.loads(fallback_path.read_text()) if fallback_path.exists() else None
arms = ["A1", "B1", "A2"] + (["B2", "A3"] if fallback_decision["run_fallback"] else [])
gates = {name: json.loads((root / "arms" / name / "gate.json").read_text()) for name in arms}
trace_arms = [name for name in arms if name.startswith("B")]
trace_pass = all((root / "arms" / name / "trace.nsys-rep").stat().st_size > 0 and (root / "arms" / name / "trace.sqlite").stat().st_size > 0 for name in trace_arms)
geometry_pass = all(value["geometry_pass"] for value in gates.values())
slo_pass = all(value["slo_pass"] for value in gates.values())
observer_valid = (fallback or primary)["pass"]
classification = "valid_observer" if observer_valid else ("observer_overhead_breach" if not fallback_decision["run_fallback"] else "observer_overhead_persists_without_cpu_sampling")
result = {
    "schema_version": 1,
    "bracket_complete": bool(geometry_pass and slo_pass and trace_pass),
    "classification": classification,
    "geometry_pass": geometry_pass,
    "slo_pass": slo_pass,
    "trace_pass": trace_pass,
    "observer_valid": observer_valid,
    "normalized_dependency_analysis_produced": False,
    "route_decision": None,
    "raw_nsys_export_only": True,
    "arms": arms,
    "primary_observer_effect": primary,
    "fallback_decision": fallback_decision,
    "fallback_observer_effect": fallback,
    "experiment_spec_sha256": os.environ["EXPERIMENT_SPEC_SHA256"],
    "model_revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881",
    "evidence_scope": "one retained Nebius L40S, vLLM 0.15.0, GLM-4.7-Flash AWQ, fixed 8192x32 c8 bracket",
    "claim_limit": "Diagnostic observer validity only; no provider-cost or intervention speedup claim.",
}
(root / "allocation-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
if not result["bracket_complete"]:
    raise SystemExit(1)
PY
phase result complete
