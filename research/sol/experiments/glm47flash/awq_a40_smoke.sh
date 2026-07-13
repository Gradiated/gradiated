#!/usr/bin/env bash
set -Eeuo pipefail
OUT=/workspace/awq-smoke; PUBLIC=/workspace/public; MODEL=/workspace/model-awq
mkdir -p "$OUT" "$PUBLIC"; HTTP=; TEL=; SERVER=
phase(){ printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"; }
package(){ python3 - <<'PY'
import hashlib,json,pathlib
p=pathlib.Path('/workspace/awq-smoke'); (p/'manifest.json').write_text(json.dumps([{'path':str(f.relative_to(p)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(p.rglob('*')) if f.is_file()],indent=2)+'\n')
PY
tar -C /workspace -czf "$PUBLIC/awq-smoke.tar.gz.tmp" awq-smoke; mv "$PUBLIC/awq-smoke.tar.gz.tmp" "$PUBLIC/awq-smoke.tar.gz"; sha256sum "$PUBLIC/awq-smoke.tar.gz" > "$PUBLIC/awq-smoke.tar.gz.sha256"; }
finish(){ rc=$?; set +e; phase teardown begin; [ -n "$SERVER" ] && kill -TERM "$SERVER" 2>/dev/null; [ -n "$TEL" ] && kill -TERM "$TEL" 2>/dev/null; wait "$SERVER" "$TEL" 2>/dev/null; phase teardown complete; package; [ "$rc" -eq 0 ] && printf 'READY\n' > "$PUBLIC/STATUS" || printf 'FAILED\n' > "$PUBLIC/STATUS"; wait "$HTTP"; }
trap finish EXIT
printf 'BOOTSTRAP\n' > "$PUBLIC/STATUS"; python3 -m http.server 8000 --bind 0.0.0.0 --directory "$PUBLIC" > "$OUT/http.stdout.log" 2> "$OUT/http.stderr.log" & HTTP=$!
phase bootstrap begin; uname -a > "$OUT/uname.txt"; nvidia-smi -q > "$OUT/nvidia-smi-q.txt" 2>&1; phase bootstrap complete
(while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.sm,clocks.mem --format=csv,noheader,nounits; sleep 1; done) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" & TEL=$!
command -v dcgmi >/dev/null && timeout 10 dcgmi dmon -c 1 > "$OUT/dcgm-one-shot.txt" 2>&1 || printf 'dcgmi unavailable or failed\n' > "$OUT/dcgm-unavailable.txt"
phase native_import begin
timeout 120 python3 - <<'PY' > "$OUT/native-import.json"
import cutlass,inspect,hashlib,json,pathlib,sglang,torch,transformers
from sglang.srt.models.glm4_moe_lite import Glm4MoeLiteForCausalLM
p=pathlib.Path(inspect.getfile(Glm4MoeLiteForCausalLM)); print(json.dumps({'class':Glm4MoeLiteForCausalLM.__name__,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'sglang':sglang.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'transformers':transformers.__version__},indent=2))
PY
phase native_import complete
phase runtime_hotfix begin
python3 - <<'PY' > "$OUT/runtime-hotfix.json"
import hashlib,json,pathlib
p=pathlib.Path('/sgl-workspace/sglang/python/sglang/srt/models/deepseek_v2.py'); before=p.read_bytes(); s=before.decode()
old='''            and not self.is_packed_weight\n            and self.fused_qkv_a_proj_with_mqa.weight.dtype == torch.bfloat16'''
new='''            and not self.is_packed_weight\n            and hasattr(self.fused_qkv_a_proj_with_mqa, "weight")\n            and self.fused_qkv_a_proj_with_mqa.weight.dtype == torch.bfloat16'''
if s.count(old)!=1: raise SystemExit('hotfix target mismatch')
p.write_text(s.replace(old,new))
print(json.dumps({'file':str(p),'purpose':'avoid dereferencing absent weight on compressed-tensors ReplicatedLinear before Hopper-only fused-path check','before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'replacement_count':1},indent=2))
PY
python3 - <<'PY' > "$OUT/runtime-hotfix-cpu.json"
import hashlib,json,pathlib
p=pathlib.Path('/sgl-workspace/sglang/python/sglang/srt/models/deepseek_common/attention_forward_methods/forward_mla_fused_rope_cpu.py'); before=p.read_bytes(); s=before.decode()
old='''            and not self.is_packed_weight\n            and self.fused_qkv_a_proj_with_mqa.weight.dtype'''
new='''            and not self.is_packed_weight\n            and hasattr(self.fused_qkv_a_proj_with_mqa, "weight")\n            and self.fused_qkv_a_proj_with_mqa.weight.dtype'''
if s.count(old)!=2: raise SystemExit('CPU hotfix target mismatch')
p.write_text(s.replace(old,new))
print(json.dumps({'file':str(p),'purpose':'guard initialization-only CPU dtype probes for compressed-tensors wrapper','before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'replacement_count':2},indent=2))
PY
phase runtime_hotfix complete
phase model_download begin
python3 - <<'PY' > "$OUT/model-download.log" 2>&1
from huggingface_hub import HfApi,snapshot_download
i=HfApi().model_info('cyankiwi/GLM-4.7-Flash-AWQ-4bit',revision='ab31d12'); print('resolved_revision='+i.sha); print(snapshot_download('cyankiwi/GLM-4.7-Flash-AWQ-4bit',revision=i.sha,local_dir='/workspace/model-awq'))
PY
sha256sum "$MODEL/config.json" "$MODEL/model.safetensors.index.json" > "$OUT/model-hashes.sha256"; du -sb "$MODEL" > "$OUT/model-size.txt"; python3 -m pip freeze > "$OUT/pip-freeze.txt"; phase model_download complete
phase model_load begin
CMD=(python3 -m sglang.launch_server --model-path "$MODEL" --served-model-name glm-4.7-flash-awq --model-impl sglang --quantization compressed-tensors --host 127.0.0.1 --port 30000 --context-length 4096 --max-running-requests 1 --max-total-tokens 4096 --max-prefill-tokens 4096 --mem-fraction-static 0.80 --chunked-prefill-size 4096 --disable-cuda-graph --disable-radix-cache --disable-shared-experts-fusion --tool-call-parser glm47 --reasoning-parser glm45 --enable-metrics --enable-request-time-stats-logging --random-seed 1234)
printf '%q ' "${CMD[@]}" > "$OUT/server-command.txt"; "${CMD[@]}" > "$OUT/server.stdout.log" 2> "$OUT/server.stderr.log" & SERVER=$!
ok=0; for _ in $(seq 1 240); do kill -0 "$SERVER" 2>/dev/null || { wait "$SERVER"; exit $?; }; curl -fsS http://127.0.0.1:30000/health >/dev/null && { ok=1; break; }; sleep 2; done; [ "$ok" -eq 1 ]; phase model_load complete
phase deterministic_completion begin; curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-before.txt"
REQ='{"model":"glm-4.7-flash-awq","messages":[{"role":"user","content":"Return a JSON object with alpha equal to 17 and beta equal to smoke."}],"temperature":0,"max_tokens":64,"seed":20260713}'
printf '%s\n' "$REQ" > "$OUT/request.json"; for i in 1 2; do curl -fsS -H 'Content-Type: application/json' -d "$REQ" http://127.0.0.1:30000/v1/chat/completions > "$OUT/response-$i.json"; done
python3 - <<'PY' > "$OUT/determinism.json"
import json,pathlib,hashlib
p=pathlib.Path('/workspace/awq-smoke'); r=[json.loads((p/f'response-{i}.json').read_text()) for i in (1,2)]; n=[{k:x['choices'][0]['message'].get(k) for k in ('content','reasoning_content','tool_calls')} for x in r]
if n[0]!=n[1]: raise SystemExit('mismatch')
print(json.dumps({'exact_normalized_identity':True,'sha256':hashlib.sha256(json.dumps(n[0],sort_keys=True).encode()).hexdigest(),'usage':[x.get('usage') for x in r]},indent=2))
PY
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-after.txt"; phase deterministic_completion complete
