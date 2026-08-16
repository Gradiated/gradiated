#!/usr/bin/env bash
set -euo pipefail
p=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_h100_v0515_ngram_verify_launch_pipeline
l=/root/workspace/research/lab/experiments/gemma4_31b/research_lab
k=/root/.config/nebius/glm-campaign/ssh_ed25519
h=/root/.config/nebius/glm-campaign/known_hosts
r=/home/glmrunner/gemma4-h100-packed-endpoint
a="$p/artifacts/staged-continuation-20260725t1401z"
mkdir -p "$a"
(while true; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$l" heartbeat --project gemma4_h100_v0515_ngram_verify_launch_pipeline >>"$a/heartbeats.log" 2>&1 || true; sleep 45; done) &
trap 'kill $! 2>/dev/null || true' EXIT
scp -i "$k" -o UserKnownHostsFile="$h" -o StrictHostKeyChecking=yes "$r" </dev/null 2>/dev/null || true
ssh -i "$k" -o UserKnownHostsFile="$h" -o StrictHostKeyChecking=yes glmrunner@89.169.103.97 "sudo docker pull docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd; python3 - <<'PY'
import hashlib,json,pathlib
r=pathlib.Path('$r'); src=r/'packet/candidate-v0.5.15/inputs/requests.jsonl'; out=r/'fresh_workload.jsonl'; rows=[]
for i,line in enumerate(src.open()):
 if i==791: break
 x=json.loads(line); x['fresh_index']=61000+i; x['prompt'][535]=261000+i; x['prompt_sha256']=hashlib.sha256(json.dumps(x['prompt']).encode()).hexdigest(); rows.append(x)
out.write_text(''.join(json.dumps(x,separators=(',',':'))+'\\n' for x in rows)); (r/'FRESH_WORKLOAD.json').write_text(json.dumps({'requests':len(rows),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'indices':[61000,61790]}))
PY" >"$a/continuation.log" 2>&1
while [ "$(date -u +%H:%M)" != "17:30" ]; do sleep 30; done
