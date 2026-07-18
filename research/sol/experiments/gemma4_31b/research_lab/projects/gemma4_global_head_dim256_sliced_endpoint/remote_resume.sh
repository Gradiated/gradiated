#!/usr/bin/env bash
set -Eeuo pipefail

remote=/home/glmrunner/gemma-attention-endpoint
workspace=$remote/workspace/global-head256-sliced
run_id=global-head256-sliced-c32-resume-20260718t2225z
run=$remote/$run_id
container=gemma-global-head256-c32
deadline_epoch=1784416800
mkdir -p "$run"

terminal() {
  python3 - "$run/OWNER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
}
fail() { terminal "$1" "$2"; exit 1; }
trap 'terminal owner_failure "$BASH_COMMAND"' ERR

(( $(date +%s) < deadline_epoch )) || fail deadline_expired before_consumer_resume
test "$(sudo docker inspect -f '{{.State.Running}}' "$container")" = true || fail server_state_failure candidate_not_running
curl -fsS http://127.0.0.1:30000/v1/models > "$run/models.json"
sha256sum "$workspace/exact_mix_runner.py" "$workspace/coherence_runner.py" > "$run/consumer-input-sha256.txt"
grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' "$run/consumer-input-sha256.txt"
cp "$remote/global-head256-transformed-tensors.json" "$run/transformed-tensors.json"
find "$remote/checkpoint" -maxdepth 1 -type f -printf '%f\t%s\n' | sort > "$run/checkpoint-before.tsv"
sudo docker inspect "$container" > "$run/container-inspect.json"
curl -fsS http://127.0.0.1:30000/get_server_info > "$run/server-info.json"

sudo docker exec "$container" python3 /work/workspace/global-head256-sliced/coherence_runner.py
cp "$remote/coherence.json" "$run/coherence.json"
curl -fsS http://127.0.0.1:30000/metrics > "$run/metrics-before-flush.prom"
curl -fsS -o "$run/flush-body.txt" -w '%{http_code}' -X POST http://127.0.0.1:30000/flush_cache > "$run/flush-status.txt"
curl -fsS http://127.0.0.1:30000/metrics > "$run/idle-metrics.prom"
test "$(cat "$run/flush-status.txt")" = 200 || fail cache_boundary_failure flush_not_http_200

sudo docker exec "$container" python3 /work/workspace/global-head256-sliced/exact_mix_runner.py \
  --output "/work/$run_id/exact-mix" --arm global_head256_sliced_triton_c32

sudo docker logs "$container" > "$run/server.log" 2>&1
sudo docker inspect "$container" > "$run/container-inspect-final.json"
curl -fsS http://127.0.0.1:30000/get_server_info > "$run/server-info-final.json"
find "$remote/checkpoint" -maxdepth 1 -type f -printf '%f\t%s\n' | sort > "$run/checkpoint-after.tsv"
cmp "$run/checkpoint-before.tsv" "$run/checkpoint-after.tsv" || fail checkpoint_mutation checkpoint_metadata_changed
python3 - "$run/OWNER_TERMINAL.json" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':True,'classification':'captured','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
cd "$remote"
tar -czf "$run_id.tar.gz" "$run_id"
