#!/usr/bin/env bash
set -Eeuo pipefail

root=${E5M2_REMOTE_ROOT:?}
artifacts="$root/component-artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"
sudo chown -R "$(id -u):$(id -g)" "$artifacts"
chmod -R u+rwX "$artifacts"
sudo docker stop gemma-layerwise-mixed-kv-candidate gemma-width16384-candidate >/dev/null 2>&1 || true

python3 - "$artifacts/INVOCATION_STATE.json" <<'PY'
import json,pathlib,time
p=pathlib.Path(__import__('sys').argv[1])
p.write_text(json.dumps({'schema_version':1,'candidate_cuda_invocation_started':False,'scientific_invocation_started':False,'updated_unix_s':time.time()},indent=2,sort_keys=True)+'\n')
PY

set +e
sudo docker run --rm --gpus all --ipc=host \
  -v "$root:/work/e5m2" \
  -e PYTHONPATH=/work/e5m2/input:/sgl-workspace/sglang/python \
  "$image" python3 /work/e5m2/input/e5m2_fa3_component.py \
    --artifact-root /work/e5m2/component-artifacts \
    --dependency-comparator "${CONTROL_SECONDS:?}" \
    >"$artifacts/component.stdout" 2>"$artifacts/component.stderr"
code=$?
set -e

python3 - "$artifacts/REMOTE_TERMINAL.json" "$code" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); invocation=p.parent/'INVOCATION_STATE.json'; component=p.parent/'COMPONENT_TERMINAL.json'
state=json.loads(invocation.read_text()) if invocation.exists() else {}
value={
  'schema_version':1,
  'status':'terminal',
  'classification':'component_complete' if int(sys.argv[2])==0 else 'component_failure',
  'exit_code':int(sys.argv[2]),
  'candidate_cuda_invocation_started':state.get('candidate_cuda_invocation_started'),
  'scientific_invocation_started':state.get('scientific_invocation_started'),
  'component_terminal_present':component.exists(),
  'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),
}
p.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
PY
exit "$code"
