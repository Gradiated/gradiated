#!/usr/bin/env bash
set -Eeuo pipefail
OUT=/workspace/glm-baseline; PUBLIC=/workspace/public; MODEL=/workspace/model
mkdir -p "$OUT" "$PUBLIC"; SERVER_PID=; TEL_PID=; DCGM_PID=; HTTP_PID=
phase(){ python3 - "$1" "$2" <<'PY' >> "$OUT/phases.jsonl"
import datetime,json,sys
print(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'phase':sys.argv[1],'state':sys.argv[2]},separators=(',',':')))
PY
}
package(){ python3 - <<'PY'
import hashlib,json,pathlib
p=pathlib.Path('/workspace/glm-baseline'); rows=[]
for f in sorted(p.rglob('*')):
 if f.is_file(): rows.append({'path':str(f.relative_to(p)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
(p/'manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
PY
tar -C /workspace -czf "$PUBLIC/glm-baseline.tar.gz.tmp" glm-baseline; mv "$PUBLIC/glm-baseline.tar.gz.tmp" "$PUBLIC/glm-baseline.tar.gz"; sha256sum "$PUBLIC/glm-baseline.tar.gz" > "$PUBLIC/glm-baseline.tar.gz.sha256"; }
finish(){ rc=$?; set +e; phase teardown begin; [ -n "$SERVER_PID" ] && kill -TERM "$SERVER_PID" 2>/dev/null; [ -n "$TEL_PID" ] && kill -TERM "$TEL_PID" 2>/dev/null; [ -n "$DCGM_PID" ] && kill -TERM "$DCGM_PID" 2>/dev/null; wait "$SERVER_PID" "$TEL_PID" "$DCGM_PID" 2>/dev/null; phase teardown complete; package; if [ "$rc" -eq 0 ]; then printf 'READY\n' > "$PUBLIC/STATUS"; else printf 'FAILED\n' > "$PUBLIC/STATUS"; fi; printf '%s\n' "$rc" > "$PUBLIC/EXIT_CODE"; wait "$HTTP_PID"; }
trap finish EXIT
printf 'BOOTSTRAP\n' > "$PUBLIC/STATUS"; python3 -m http.server 8000 --bind 0.0.0.0 --directory "$PUBLIC" > "$OUT/artifact-server.stdout.log" 2> "$OUT/artifact-server.stderr.log" & HTTP_PID=$!
phase bootstrap begin; uname -a > "$OUT/uname.txt"; nvidia-smi -q > "$OUT/nvidia-smi-q.txt" 2>&1; phase bootstrap complete
phase telemetry begin
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.sm,clocks.mem --format=csv,noheader,nounits; sleep 1; done) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" & TEL_PID=$!
if command -v dcgmi >/dev/null; then timeout 3300 dcgmi dmon -e 1002,1003,1004,1005,1009 -d 1000 > "$OUT/dcgm-dmon.txt" 2> "$OUT/dcgm-dmon.stderr.log" & DCGM_PID=$!; else printf 'dcgmi unavailable\n' > "$OUT/dcgm-unavailable.txt"; fi
phase telemetry active
phase native_import begin
timeout 120 python3 - <<'PY' > "$OUT/native-import.json"
import cutlass,inspect,hashlib,json,pathlib,sglang,torch,transformers
from sglang.srt.models.glm4_moe_lite import Glm4MoeLiteForCausalLM
p=pathlib.Path(inspect.getfile(Glm4MoeLiteForCausalLM)); print(json.dumps({'class':Glm4MoeLiteForCausalLM.__name__,'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'sglang':sglang.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'transformers':transformers.__version__},indent=2))
PY
phase native_import complete
phase model_download begin
python3 - <<'PY' > "$OUT/model-download.log" 2>&1
from huggingface_hub import HfApi,snapshot_download
i=HfApi().model_info('zai-org/GLM-4.7-Flash',revision='75fce70'); print('resolved_revision='+i.sha); print(snapshot_download('zai-org/GLM-4.7-Flash',revision=i.sha,local_dir='/workspace/model'))
PY
sha256sum "$MODEL/config.json" "$MODEL/model.safetensors.index.json" > "$OUT/model-hashes.sha256"; du -sb "$MODEL" > "$OUT/model-size.txt"; python3 -m pip freeze > "$OUT/pip-freeze.txt"; phase model_download complete
phase model_load begin
CMD=(python3 -m sglang.launch_server --model-path "$MODEL" --served-model-name glm-4.7-flash --model-impl sglang --host 127.0.0.1 --port 30000 --tp-size 1 --context-length 16384 --max-running-requests 32 --mem-fraction-static 0.90 --chunked-prefill-size 8192 --disable-radix-cache --tool-call-parser glm47 --reasoning-parser glm45 --enable-metrics --enable-request-time-stats-logging --random-seed 1234)
printf '%q ' "${CMD[@]}" > "$OUT/server-command.txt"; "${CMD[@]}" > "$OUT/server.stdout.log" 2> "$OUT/server.stderr.log" & SERVER_PID=$!
ready=0; for _ in $(seq 1 240); do kill -0 "$SERVER_PID" 2>/dev/null || { wait "$SERVER_PID"; exit $?; }; curl -fsS http://127.0.0.1:30000/health >/dev/null && { ready=1; break; }; sleep 2; done; [ "$ready" -eq 1 ]; phase model_load complete
run_bench(){ label=$1; prompts=$2; concurrency=$3; deadline=$4; phase "$label" begin; curl -fsS http://127.0.0.1:30000/metrics > "$OUT/$label.metrics-before.txt"; python3 -m sglang.bench_serving --backend sglang --base-url http://127.0.0.1:30000 --model glm-4.7-flash --tokenizer "$MODEL" --dataset-name random --random-input-len 8192 --random-output-len 1024 --random-range-ratio 1 --num-prompts "$prompts" --max-concurrency "$concurrency" --seed 20260713 --disable-tqdm --output-file "$OUT/$label.json" > "$OUT/$label.stdout.log" 2> "$OUT/$label.stderr.log" & BP=$!; end=$(( $(date +%s)+deadline )); while kill -0 "$BP" 2>/dev/null; do kill -0 "$SERVER_PID" 2>/dev/null || { kill -TERM "$BP"; wait "$SERVER_PID"; exit $?; }; [ "$(date +%s)" -lt "$end" ] || { kill -TERM "$BP"; return 124; }; sleep 2; done; wait "$BP"; curl -fsS http://127.0.0.1:30000/metrics > "$OUT/$label.metrics-after.txt"; phase "$label" complete; }
run_bench baseline-c1 2 1 600
run_bench baseline-c8 16 8 900
run_bench baseline-c32 256 32 1500
