#!/usr/bin/env bash
set -euo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h100_v0515_ngram_verify_launch_pipeline
source_project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h100_v0515_ngram_price_normalized
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
host=89.169.103.97
remote=/home/glmrunner/gemma4-h100-packed-endpoint
artifact="$project/artifacts/fresh-endpoint-hostkey-20260725t1328z"
mkdir -p "$artifact"
heartbeat() { PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_h100_v0515_ngram_verify_launch_pipeline >>"$artifact/heartbeats.log" 2>&1 || true; }
while true; do heartbeat; sleep 45; done &
hb=$!
trap 'kill "$hb" 2>/dev/null || true' EXIT
ssh -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes glmrunner@"$host" "mkdir -p '$remote/.checkpoint.staging' '$remote/.packet.staging' '$remote/out'; nvidia-smi --query-gpu=name,memory.used --format=csv,noheader" >"$artifact/guest_readiness.txt"
tar -C "$source_project/inputs/checkpoint" -cf - . | ssh -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes glmrunner@"$host" "tar -C '$remote/.checkpoint.staging' -xf -"
tar -C "$source_project/packet" -cf - . | ssh -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes glmrunner@"$host" "tar -C '$remote/.packet.staging' -xf -"
tar -C "$project/exact_runtime_source" -cf - . | ssh -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes glmrunner@"$host" "mkdir -p '$remote/runtime-source'; tar -C '$remote/runtime-source' -xf -"
scp -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes "$source_project/packet/CHECKPOINT_MANIFEST.json" glmrunner@"$host":"$remote/"
ssh -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes glmrunner@"$host" "python3 - <<'PY'
import hashlib,json,pathlib
r=pathlib.Path('$remote'); m=json.load(open(r/'CHECKPOINT_MANIFEST.json')); bad=[]
for x in m['files']:
 p=r/'.checkpoint.staging'/x['name']; h=hashlib.sha256(p.read_bytes()).hexdigest()
 if p.stat().st_size!=x['bytes'] or h!=x['sha256']: bad.append(x['name'])
assert not bad,bad
(r/'CHECKPOINT_STAGE_VERIFIED.json').write_text(json.dumps({'pass':True,'files':len(m['files'])}))
PY
rm -rf '$remote/checkpoint' '$remote/packet'; mv '$remote/.checkpoint.staging' '$remote/checkpoint'; mv '$remote/.packet.staging' '$remote/packet'; chmod -R a-w '$remote/checkpoint' '$remote/packet' '$remote/runtime-source'"
date -u +%Y-%m-%dT%H:%M:%SZ >"$artifact/STAGING_COMPLETE_UTC.txt"
