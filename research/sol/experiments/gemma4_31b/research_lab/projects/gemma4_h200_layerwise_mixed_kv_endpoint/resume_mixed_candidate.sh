#!/usr/bin/env bash
set -Eeuo pipefail

root=${MIXED_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/endpoint-artifacts"
container=gemma-layerwise-mixed-kv-candidate

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
x=json.loads(p.read_text())
x[sys.argv[2]]=True; x['updated_unix_s']=time.time(); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

finalize() {
  set +e
  sudo docker logs "$container" >"$artifacts/candidate.server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/candidate.container-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/compact.tar.gz" >"$root/compact.tar.gz.sha256"
}
trap finalize EXIT

python3 - "$artifacts/INVOCATION_STATE.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get('component_started') is True
assert x.get('candidate_science_started') is False
PY
curl -fsS http://127.0.0.1:30000/v1/models >/dev/null
test ! -e "$artifacts/candidate"
cp "$artifacts/COMPONENT_RESULT.json" "$artifacts/COMPONENT_RESULT.invalid-guard.json"

sudo docker exec "$container" python3 /work/mixed/input/resume_component_path_check.py \
  /work/mixed/endpoint-artifacts/mixed-kv-audit \
  /work/mixed/endpoint-artifacts/COMPONENT_RESULT.invalid-guard.json \
  /work/mixed/endpoint-artifacts/COMPONENT_RESULT.json \
  /work/mixed/endpoint-artifacts/candidate.server-args.txt \
  /work/mixed/endpoint-artifacts/candidate.server-start.log \
  >"$artifacts/component-repair.stdout" 2>"$artifacts/component-repair.stderr"
state component_passed

state candidate_science_started
sudo docker exec "$container" python3 /work/mixed/input/fp8_qkv_paired_runner.py \
  --output /work/mixed/endpoint-artifacts/candidate \
  --arm layerwise_mixed_e4m3_local_e5m2_global \
  --concurrency 32 >"$artifacts/candidate.runner.stdout" 2>"$artifacts/candidate.runner.stderr"

python3 "$input/finalize_mixed_endpoint.py" \
  "$artifacts/candidate/TERMINAL.json" \
  "$artifacts/candidate/WORKLOAD.json" \
  "$artifacts/COMPONENT_RESULT.json" \
  "$artifacts/ENDPOINT_RESULT.json" \
  "$artifacts/candidate.server-args.txt"
python3 - "$artifacts/WORKER_TERMINAL.json" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
value={'schema_version':1,'status':'terminal','classification':'completed','message':'candidate_scientific_terminal_persisted_after_telemetry_guard_repair','timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
