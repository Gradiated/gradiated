#!/usr/bin/env bash
set -Eeuo pipefail

remote=/home/glmrunner/gemma-local-kv8
bound=$remote/phase2-consumer-bound
checkpoint=$remote/checkpoint
producer_run=$remote/local-kv8-conversion-20260719t-phase2
overlay=$producer_run/distillation/overlay.safetensors
expected_overlay=e29faa6768d22aa6cae56bb15253d02f6af0aca2abdd6d4f0092a436cea05780
run_id=local-kv8-consumer-resume-20260719t1500
run=$remote/$run_id
image='docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a'
container=gemma-local-kv8-converted-c32
deadline_epoch="${DEADLINE_EPOCH:?missing DEADLINE_EPOCH}"
packaged=0

terminal() { python3 - "$run/OWNER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
}
capture() { sudo docker logs "$container" > "$run/server.log" 2>&1 || true; sudo docker inspect "$container" > "$run/container-inspect-final.json" 2>&1 || true; nvidia-smi -q > "$run/nvidia-smi-final.txt" 2>&1 || true; }
package() { (( packaged == 0 )) || return; packaged=1; cd "$remote"; tar -czf "$run_id.tar.gz" "$run_id"; sha256sum "$run_id.tar.gz" > "$run_id.tar.gz.sha256"; }
fail() { trap - ERR; capture; terminal "$1" "$2"; package; exit 0; }
onerr() { local x=$?; trap - ERR; capture; printf '%s\n' "exit=$x command=$BASH_COMMAND" > "$run/PREINVOCATION_FAILURE.txt"; exit 42; }
trap onerr ERR

mkdir -p "$run"
(( $(date +%s) < deadline_epoch )) || exit 43
test -f "$overlay" && test "$(sha256sum "$overlay" | awk '{print $1}')" = "$expected_overlay"
test -f "$checkpoint/config.json"
sudo docker image inspect "$image" > "$run/image-inspect.json"
sudo docker rm -f "$container" > "$run/stopped-container.txt" 2>&1 || true
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -e SGLANG_GEMMA4_LOCAL_KV8=1 \
  -e SGLANG_GEMMA4_LOCAL_KV8_MANIFEST=/work/local-kv8-transformed-tensors.json \
  -e SGLANG_GEMMA4_LOCAL_KV8_OVERLAY=/work/local-kv8-conversion-20260719t-phase2/distillation/overlay.safetensors \
  -e SGLANG_GEMMA4_LOCAL_KV8_OVERLAY_SHA256="$expected_overlay" \
  -v "$remote:/work" -v "$checkpoint:/work/checkpoint:ro" -v "$bound:/bound:ro" -v "$run:/output" \
  -v "$bound/gemma4_causal.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py:ro" \
  -v "$bound/gemma4_mm.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_mm.py:ro" \
  -v "$bound/model_config.py:/sgl-workspace/sglang/python/sglang/srt/configs/model_config.py:ro" \
  "$image" python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 \
  --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 --context-length 12000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 --max-prefill-tokens 16384 --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8 --stream-interval 1 > "$run/container-id.txt"
ready=0; for x in $(seq 1 180); do (( $(date +%s) < deadline_epoch )) || fail deadline_expired server_startup; if curl -fsS http://127.0.0.1:30000/v1/models > "$run/models.json" 2> "$run/models.stderr"; then ready=1; break; fi; sleep 4; done
sudo docker logs "$container" > "$run/server-start.log" 2>&1 || true
(( ready == 1 )) || fail startup_failure server_not_ready
sudo docker exec "$container" python3 /bound/coherence_runner.py > "$run/coherence.stdout" 2> "$run/coherence.stderr" || fail coherence_runtime_failure runner_failed
cp "$remote/coherence.json" "$run/coherence.json"
python3 - "$run/coherence.json" <<'PY' || fail coherence_negative one_or_more_rules_failed
import json,sys
x=json.load(open(sys.argv[1])); raise SystemExit(0 if x.get('pass') and len(x.get('rows',[]))==3 and all(r.get('rule_pass') for r in x['rows']) else 2)
PY
sudo docker exec "$container" python3 /bound/retrieval_10k_runner.py --checkpoint /work/checkpoint --output /output/retrieval-10k > "$run/retrieval.stdout" 2> "$run/retrieval.stderr" || fail retrieval_negative deterministic_10k_gate_failed
python3 - "$run/retrieval-10k/TERMINAL.json" <<'PY' || fail retrieval_negative deterministic_10k_gate_failed
import json,sys
x=json.load(open(sys.argv[1])); raise SystemExit(0 if x.get('pass') and x.get('cases')==3 and x.get('exact_matches')==3 else 2)
PY
curl -fsS http://127.0.0.1:30000/metrics > "$run/metrics-before-endpoint.prom"
curl -fsS -o "$run/flush-body.txt" -w '%{http_code}' -X POST http://127.0.0.1:30000/flush_cache > "$run/flush-status.txt"
test "$(cat "$run/flush-status.txt")" = 200 || fail cache_boundary_failure flush_not_http_200
sudo docker exec "$container" python3 /bound/exact_mix_runner.py --output /output/exact-mix --arm local_kv8_distilled_triton_c32 > "$run/exact.stdout" 2> "$run/exact.stderr" || fail endpoint_runtime_failure exact_runner_failed
capture
python3 - "$run/OWNER_TERMINAL.json" "$run/exact-mix/TERMINAL.json" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); x=json.load(open(sys.argv[2])); c=x.get('cache',{}); valid=bool(x.get('pass') and x.get('complete_requests')==32 and c.get('cached_prompt_tokens_delta')==17120 and c.get('uncached_prompt_tokens_delta')==117728); v=x.get('service_seconds_per_request'); retained=bool(valid and v is not None and v < .9194573941250042); promoted=bool(valid and v is not None and v <= .8734845244187539); q=p.with_suffix('.part'); q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':'broad_quality_promote' if promoted else ('retained_improvement' if retained else 'endpoint_negative'),'pass':retained,'performance_valid':valid,'broad_quality_promoted':promoted,'service_seconds_per_request':v,'candidate':x,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
package
