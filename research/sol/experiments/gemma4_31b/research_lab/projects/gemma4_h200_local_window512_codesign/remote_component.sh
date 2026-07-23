#!/usr/bin/env bash
set -Eeuo pipefail

root=${WINDOW512_REMOTE_ROOT:?}
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
artifacts="$root/component-artifacts"
mkdir -p "$artifacts"
python3 - "$artifacts/INVOCATION_STATE.json" <<'PY'
import json, pathlib, time
p=pathlib.Path(__import__('sys').argv[1])
p.write_text(json.dumps({'schema_version':1,'candidate_cuda_invocation_started':False,'scientific_invocation_started':False,'updated_unix_s':time.time()},indent=2)+'\n')
PY
set +e
sudo docker run --rm --gpus all --ipc=host \
  -v "$root:/work" \
  -e PYTHONPATH=/sgl-workspace/sglang/python \
  "$image" \
  python3 /work/input/window_component.py \
    --artifact-root /work/component-artifacts \
    >"$artifacts/component.stdout" 2>"$artifacts/component.stderr"
code=$?
set -e
python3 - "$artifacts/REMOTE_TERMINAL.json" "$code" <<'PY'
import datetime, json, pathlib, sys
p=pathlib.Path(sys.argv[1])
component=p.parent/'COMPONENT_TERMINAL.json'
invocation=p.parent/'INVOCATION_STATE.json'
value={
  'schema_version':1,
  'status':'terminal',
  'classification':'component_complete' if int(sys.argv[2])==0 else 'component_failure',
  'exit_code':int(sys.argv[2]),
  'candidate_cuda_invocation_started':json.loads(invocation.read_text()).get('candidate_cuda_invocation_started',False) if invocation.exists() else None,
  'scientific_invocation_started':json.loads(invocation.read_text()).get('scientific_invocation_started',False) if invocation.exists() else None,
  'component_terminal_present':component.exists(),
  'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),
}
p.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
PY
exit "$code"
