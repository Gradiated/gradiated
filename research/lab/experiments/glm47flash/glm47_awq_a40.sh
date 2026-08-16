#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/glm-awq-a40
MODEL=/workspace/model-awq
ARCHIVE=/workspace/glm-awq-a40.tar.gz
mkdir -p "$OUT"
rm -f /workspace/LIVE /workspace/READY /workspace/FAILED "$ARCHIVE" "$ARCHIVE.sha256"
exec > >(tee -a "$OUT/orchestrator.stdout.log") 2> >(tee -a "$OUT/orchestrator.stderr.log" >&2)

HTTP=
TEL=
SERVER=

stop_process() {
  local pid=${1:-}
  if [[ -n "$pid" ]]; then
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}

package_results() {
  python3 - <<'PY'
import hashlib
import json
import pathlib

p = pathlib.Path('/workspace/glm-awq-a40')
manifest = []
for f in sorted(p.iterdir()):
    if f.is_file():
        manifest.append({'name': f.name, 'bytes': f.stat().st_size, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()})
(p / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
  tar -C /workspace -czf "$ARCHIVE" glm-awq-a40
  sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
}

fail() {
  local code=$?
  set +e
  stop_process "$SERVER"
  stop_process "$TEL"
  date -u +%FT%TZ > "$OUT/failed_at.txt"
  printf '%s\n' "$code" > "$OUT/exit_code.txt"
  package_results
  printf 'failed\n' > /workspace/FAILED
  wait "$HTTP"
}
trap fail ERR

python3 -m http.server 8000 --directory /workspace > "$OUT/http.stdout.log" 2> "$OUT/http.stderr.log" &
HTTP=$!
printf 'live\n' > /workspace/LIVE
date -u +%FT%TZ > "$OUT/started_at.txt"
nvidia-smi -q > "$OUT/nvidia-smi-q.txt"
python3 -m pip freeze > "$OUT/pip-freeze.txt"
python3 - <<'PY' > "$OUT/environment.json"
import json
import platform
import sglang
import torch

print(json.dumps({'python': platform.python_version(), 'torch': torch.__version__, 'cuda': torch.version.cuda, 'sglang': sglang.__version__}, indent=2))
PY

python3 - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download('cyankiwi/GLM-4.7-Flash-AWQ-4bit', revision='ab31d12', local_dir='/workspace/model-awq')
PY
sha256sum "$MODEL/config.json" "$MODEL/model.safetensors.index.json" > "$OUT/model-hashes.sha256"
du -sb "$MODEL" > "$OUT/model-size.txt"

telemetry() {
  while true; do
    nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.sm --format=csv,noheader,nounits
    sleep 1
  done
}
telemetry > "$OUT/telemetry.csv" 2> "$OUT/telemetry.err" &
TEL=$!

wait_ready() {
  for _ in $(seq 1 300); do
    curl -fsS http://127.0.0.1:30000/health >/dev/null && return 0
    sleep 2
  done
  return 1
}

SGLANG_ENABLE_SPEC_V2=True python3 -m sglang.launch_server \
  --model-path "$MODEL" --served-model-name glm-4.7-flash-awq \
  --host 127.0.0.1 --port 30000 --context-length 16384 \
  --mem-fraction-static 0.90 --chunked-prefill-size 8192 \
  --enable-metrics --enable-request-time-stats-logging \
  --random-seed 1234 --disable-radix-cache \
  > "$OUT/server.stdout.log" 2> "$OUT/server.stderr.log" &
SERVER=$!
wait_ready

bench() {
  local label=$1
  local prompts=$2
  local concurrency=$3
  python3 -m sglang.bench_serving --backend sglang --base-url http://127.0.0.1:30000 \
    --model glm-4.7-flash-awq --tokenizer "$MODEL" --dataset-name random \
    --random-input-len 8192 --random-output-len 1024 --random-range-ratio 1 \
    --num-prompts "$prompts" --max-concurrency "$concurrency" --seed 20260713 \
    --output-file "$OUT/${label}.json" --disable-tqdm \
    > "$OUT/${label}.stdout.log" 2> "$OUT/${label}.stderr.log"
}

bench awq-c1 5 1
bench awq-c8 40 8
bench awq-c32 160 32
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/server.metrics.txt"
stop_process "$SERVER"
SERVER=
stop_process "$TEL"
TEL=
date -u +%FT%TZ > "$OUT/finished_at.txt"
package_results
printf 'ready\n' > /workspace/READY
trap - ERR
wait "$HTTP"
