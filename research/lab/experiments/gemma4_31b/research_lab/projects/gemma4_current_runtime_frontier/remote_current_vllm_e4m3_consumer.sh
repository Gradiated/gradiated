#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-current-vllm
input="$root/input"
out="$root/artifacts/current-vllm-e4m3-h200"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

finish() {
  rc=$?
  test -f "$out/CONSUMER_TERMINAL.json" || atomic "$out/CONSUMER_TERMINAL.json" integration_failure "consumer exit $rc"
  exit "$rc"
}
trap finish EXIT

(cd "$input" && sha256sum -c INPUTS.sha256)
curl -fsS http://127.0.0.1:30000/v1/models >"$out/models-consumer.json"
test -s "$out/KV_CACHE_CONSUMER.json"
grep -F 'fp8_e4m3' "$out/kv-cache-consumer.log" >/dev/null
printf '%s\n' '{"candidate_science_started":false,"stage":"warmup_before_c32"}' >"$out/CONSUMER_INVOCATION_STATE.json"
python3 "$input/current_vllm_exact_mix_runner.py" --output "$out/exact-c32-r1" --arm current_vllm_fp8e4m3_c32 --concurrency 32 --provider-hourly-usd 2.46 --invocation-state-file "$out/CONSUMER_INVOCATION_STATE.json"
python3 - "$out/exact-c32-r1/TERMINAL.json" "$out/CONSUMER_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
x=json.load(open(sys.argv[1])); p=pathlib.Path(sys.argv[2]); q=p.with_suffix('.part')
classification='measured_endpoint' if x['pass'] else 'endpoint_gate_failure'
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':classification,'terminal':x},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
