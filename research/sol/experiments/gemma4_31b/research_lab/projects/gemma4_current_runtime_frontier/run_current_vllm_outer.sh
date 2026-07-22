#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_current_runtime_frontier
artifacts="$project/artifacts/current-vllm-h200-20260722t1231z"
remote=/home/glmrunner/gemma4-current-vllm
ip=195.242.29.186
key=/root/.config/gradiated/providers/gcore/id_ed25519
ssh_opts=(-i "$key" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30)
mkdir -p "$artifacts"

terminal() {
  python3 - "$artifacts/OUTER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
}

retrieve() {
  mkdir -p "$artifacts/remote-retrieved"
  ssh "${ssh_opts[@]}" "glmrunner@$ip" "test -d $remote/artifacts && tar -C $remote/artifacts -cf - ." | tar -C "$artifacts/remote-retrieved" -xf - >"$artifacts/retrieve.stdout.log" 2>"$artifacts/retrieve.stderr.log" || return 1
}

finish() {
  rc=$?
  retrieve || true
  if test -f "$artifacts/remote-retrieved/WORKER_TERMINAL.json"; then
    cp "$artifacts/remote-retrieved/WORKER_TERMINAL.json" "$artifacts/WORKER_TERMINAL.json"
    terminal remote_terminal_retrieved "remote worker terminal retrieved"
    condition=ready
  else
    terminal retrieval_failure "remote worker terminal unavailable after exit $rc"
    python3 - "$artifacts/REPAIR_READY.json" "$rc" <<'PY'
import json,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); p.write_text(json.dumps({'schema_version':1,'status':'repair_ready','diagnostic':'pre-invocation remote access/retrieval failure','exit_code':int(sys.argv[2]),'repair_deadline_epoch':time.time()+900},indent=2,sort_keys=True)+'\n')
PY
    exit "$rc"
  fi
  PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab /root/workspace/research/sol/experiments/gemma4_31b/research_lab release --project gemma4_current_runtime_frontier --condition "$condition" >>"$artifacts/release.log" 2>&1 || true
  exit "$rc"
}
trap finish EXIT

ssh "${ssh_opts[@]}" "glmrunner@$ip" "mkdir -p $remote/input $remote/artifacts $remote/checkpoint"
tar -C "$project/inputs" --exclude='./checkpoint' -cf - . | ssh "${ssh_opts[@]}" "glmrunner@$ip" "tar -C $remote/input -xf -" >"$artifacts/input-transfer.stdout.log" 2>"$artifacts/input-transfer.stderr.log"
tar -C "$project/inputs/checkpoint" -cf - . | ssh "${ssh_opts[@]}" "glmrunner@$ip" "tar -C $remote/checkpoint -xf -" >"$artifacts/checkpoint-transfer.stdout.log" 2>"$artifacts/checkpoint-transfer.stderr.log"
cat "$project/remote_current_vllm_h200.sh" | ssh "${ssh_opts[@]}" "glmrunner@$ip" "cat > $remote/remote_current_vllm_h200.sh && chmod 700 $remote/remote_current_vllm_h200.sh"
ssh "${ssh_opts[@]}" "glmrunner@$ip" "cd $remote/checkpoint && sha256sum model.safetensors.index.json config.json tokenizer.json > $remote/artifacts/checkpoint-identity.sha256 && bash $remote/remote_current_vllm_h200.sh" >"$artifacts/remote.stdout.log" 2>"$artifacts/remote.stderr.log"
