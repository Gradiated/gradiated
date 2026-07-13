#!/usr/bin/env bash
set -u
OUT=/workspace/glm-campaign
MODEL=/workspace/model
mkdir -p "$OUT"
exec > >(tee -a "$OUT/orchestrator.stdout.log") 2> >(tee -a "$OUT/orchestrator.stderr.log" >&2)
date -u +%FT%TZ > "$OUT/started_at.txt"
nvidia-smi -q > "$OUT/nvidia-smi-q.txt" || true
python3 -m pip freeze > "$OUT/pip-freeze.txt" || true
python3 - <<'PY' > "$OUT/environment.json"
import json,platform,torch,sglang
print(json.dumps({'python':platform.python_version(),'torch':torch.__version__,'cuda':torch.version.cuda,'sglang':sglang.__version__},indent=2))
PY

python3 - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('zai-org/GLM-4.7-Flash', revision='75fce70', local_dir='/workspace/model')
PY
sha256sum "$MODEL/config.json" "$MODEL/model.safetensors.index.json" > "$OUT/model-hashes.sha256"
du -sb "$MODEL" > "$OUT/model-size.txt"

telemetry() {
  while true; do
    nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.sm --format=csv,noheader,nounits
    sleep 1
  done
}
telemetry > "$OUT/telemetry.csv" 2> "$OUT/telemetry.err" & TEL=$!

wait_ready() {
  for i in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/health >/dev/null && return 0; sleep 2; done
  return 1
}
launch() {
  label=$1; shift
  SGLANG_ENABLE_SPEC_V2=True python3 -m sglang.launch_server \
    --model-path "$MODEL" --served-model-name glm-4.7-flash \
    --host 127.0.0.1 --port 30000 --context-length 16384 \
    --mem-fraction-static 0.90 --chunked-prefill-size 8192 \
    --enable-metrics --enable-request-time-stats-logging \
    --random-seed 1234 "$@" > "$OUT/server-${label}.stdout.log" 2> "$OUT/server-${label}.stderr.log" &
  SERVER=$!
  wait_ready
}
stop_server() { kill -TERM "$SERVER" 2>/dev/null || true; wait "$SERVER" 2>/dev/null || true; sleep 5; }
bench() {
  label=$1; n=$2; c=$3
  python3 -m sglang.bench_serving --backend sglang --base-url http://127.0.0.1:30000 \
    --model glm-4.7-flash --tokenizer "$MODEL" --dataset-name random \
    --random-input-len 8192 --random-output-len 1024 --random-range-ratio 1 \
    --num-prompts "$n" --max-concurrency "$c" --seed 20260713 \
    --output-file "$OUT/${label}.json" --disable-tqdm > "$OUT/${label}.stdout.log" 2> "$OUT/${label}.stderr.log"
}

launch stock --disable-radix-cache
bench stock-c1 4 1
bench stock-c8 32 8
bench stock-c32 256 32
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/stock.metrics.txt" || true
stop_server

launch mtp --disable-radix-cache --speculative-algorithm NEXTN \
  --speculative-num-steps 1 --speculative-eagle-topk 1 --speculative-num-draft-tokens 2
bench mtp-c32 256 32
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/mtp.metrics.txt" || true
stop_server

kill "$TEL" 2>/dev/null || true
wait "$TEL" 2>/dev/null || true
date -u +%FT%TZ > "$OUT/finished_at.txt"
python3 - <<'PY'
import json,pathlib,hashlib
p=pathlib.Path('/workspace/glm-campaign')
manifest=[]
for f in sorted(p.iterdir()):
 if f.is_file(): manifest.append({'name':f.name,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
(p/'manifest.json').write_text(json.dumps(manifest,indent=2))
PY
tar -C /workspace -czf /workspace/glm-attempt1.tar.gz glm-campaign
sha256sum /workspace/glm-attempt1.tar.gz > /workspace/glm-attempt1.tar.gz.sha256
printf 'ready\n' > /workspace/READY
cd /workspace && python3 -m http.server 8000
