#!/usr/bin/env bash
set -Eeuo pipefail

root=${UPSTREAM_REBASE_ROOT:?}
out="$root/out"
mkdir -p "$out"

attempt() {
  python3 - "$out" "$1" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1])/'ATTEMPT_TERMINAL.json'; q=p.with_suffix('.json.part')
q.write_text(json.dumps({'classification':'recoverable_integration_or_typed_runtime_failure','error':sys.argv[2],'candidate_sample_consumed':False},sort_keys=True,indent=2)+'\n'); q.replace(p)
PY
}
trap 'attempt "worker_failed_at_line_${LINENO}"' ERR

if sudo docker inspect -f '{{.State.Running}}' gemma4-ngram-upstream-v0515 2>/dev/null | grep -qx true; then
  UPSTREAM_REBASE_ROOT="$root" UPSTREAM_REBASE_OUT="$out" \
    sudo -E python3 "$root/remote_runtime_discriminator.py"
  exit 0
fi

python3 - "$root" <<'PY'
import json, pathlib, subprocess, sys
r=pathlib.Path(sys.argv[1]); rows=[]
for name in ('gemma4-ngram-tail-overlap','gemma4-ngram-upstream-v0515'):
    x=subprocess.run(['sudo','docker','inspect',name],text=True,capture_output=True)
    rows.append({'name':name,'returncode':x.returncode,'stdout':x.stdout[-12000:],'stderr':x.stderr[-2000:]})
(r/'PRE_REPLACEMENT_CONTAINERS.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')
PY
sudo docker rm -f gemma4-ngram-tail-overlap gemma4-ngram-upstream-v0515 >/dev/null 2>&1 || true
sudo docker pull 'docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd'
mapfile -t args < <(python3 - "$root/inputs/ngram-launch.json" <<'PY'
import json,sys
for x in json.load(open(sys.argv[1]))['args']: print(x)
PY
)
sudo docker run -d --gpus all --network host --ipc host --name gemma4-ngram-upstream-v0515 \
  -v /home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint:/work/checkpoint:ro \
  'docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd' \
  python3 -m sglang.launch_server "${args[@]}"
UPSTREAM_REBASE_ROOT="$root" UPSTREAM_REBASE_OUT="$out" \
  sudo -E python3 "$root/remote_runtime_discriminator.py"
