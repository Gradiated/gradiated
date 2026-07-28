#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_dflash_endpoint
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
ip=89.169.109.132
remote=/home/glmrunner/gemma4-dflash
out=$1
archive=$2
mkdir -p "$out"
exec >> "$out/owner.log" 2>&1
export PYTHONPATH=/root/workspace/research/factory/src
pool=(python3 -m grad_research.gpu_pool --lab "$lab")
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$known" -o ConnectTimeout=10 "glmrunner@$ip")
scp=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$known" -o ConnectTimeout=10)
terminal=false
heartbeat() { while sleep 45; do "${pool[@]}" heartbeat --project gemma4_h200_dflash_endpoint >> "$out/heartbeat.log" 2>&1 || true; done; }
echo '{"event":"owner_started","timestamp":"'"$(date -u +%FT%TZ)"'}' > "$out/owner-events.jsonl"
archive_sha=$(sha256sum "$archive" | awk '{print $1}')
expected_archive_sha=$(python3 -c 'import json; print(json.load(open("'"$project/DIRECTOR_TIED_HEAD_ADAPTER_FRESH_H200_BINDING.json"'"))["execution_packet"]["archive_sha256"])')
if [[ "$archive_sha" != "$expected_archive_sha" ]]; then
  echo "typed_input_hash_mismatch:$archive_sha" >&2
  exit 65
fi
echo pretransfer_remote_mkdir
"${ssh[@]}" "mkdir -p $remote"
heartbeat & hb=$!
trap 'kill "$hb" 2>/dev/null || true; wait "$hb" 2>/dev/null || true' EXIT
"${scp[@]}" "$archive" "glmrunner@$ip:$remote/tied-head-adapter-inputs-20260725.tar"
"${scp[@]}" "$project/remote_stage_tied_head_adapter.sh" "glmrunner@$ip:$remote/remote_stage_tied_head_adapter.sh"
"${ssh[@]}" "rm -rf $remote/tied-head-adapter-inputs-20260725 && mkdir -p $remote/tied-head-adapter-inputs-20260725 && tar -xf $remote/tied-head-adapter-inputs-20260725.tar -C $remote/tied-head-adapter-inputs-20260725"
"${ssh[@]}" "chmod 700 $remote/remote_stage_tied_head_adapter.sh && bash $remote/remote_stage_tied_head_adapter.sh"
"${ssh[@]}" "sudo docker rm -f gemma4-dflash >/dev/null 2>&1 || true; tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf $remote/tied-head-adapter-terminal.tar.gz -C $remote/work tied-head-adapter RESIDENT_MANIFEST.json RESIDENT_MANIFEST.sha256 PHASE.resident_manifest"
"${scp[@]}" "glmrunner@$ip:$remote/tied-head-adapter-terminal.tar.gz" "$out/tied-head-adapter-terminal.tar.gz"
mkdir -p "$out/retrieved"
tar -xzf "$out/tied-head-adapter-terminal.tar.gz" -C "$out/retrieved"
test -f "$out/retrieved/tied-head-adapter/REMOTE_TERMINAL.json"
if [[ -f "$out/retrieved/tied-head-adapter/FINAL_TERMINAL.json" ]]; then terminal=true; fi
if [[ "$terminal" != true ]]; then echo 'scientific terminal missing; claim retained for repair' >&2; exit 72; fi
contents="$out/BENCH_CONTENTS.json"
printf '%s\n' '{"project":"gemma4_h200_dflash_endpoint","server_state":"stopped by owner; exact models, source, image, caches and resident manifest remain"}' > "$contents"
"${pool[@]}" release --project gemma4_h200_dflash_endpoint --condition ready --contents "$contents"
echo '{"event":"scientific_terminal_retrieved_and_released","timestamp":"'"$(date -u +%FT%TZ)"'}' >> "$out/owner-events.jsonl"
