#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_current_runtime_frontier
artifacts="$project/artifacts/current-vllm-e4m3-consumer-20260722t1350z"
remote=/home/glmrunner/gemma4-current-vllm
ip=195.242.29.186
key=/root/.config/gradiated/providers/gcore/id_ed25519
ssh_opts=(-i "$key" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30)
mkdir -p "$artifacts"

heartbeat() {
  while true; do
    PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab /root/workspace/research/lab/experiments/gemma4_31b/research_lab heartbeat --project gemma4_current_runtime_frontier >>"$artifacts/heartbeat.log" 2>&1 || true
    sleep 45
  done
}

terminal() {
  python3 - "$artifacts/OUTER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
}

retrieve() {
  mkdir -p "$artifacts/remote-retrieved"
  ssh "${ssh_opts[@]}" "glmrunner@$ip" "test -d $remote/artifacts && tar -C $remote/artifacts -cf - ." | tar -C "$artifacts/remote-retrieved" -xf - >"$artifacts/retrieve.stdout.log" 2>"$artifacts/retrieve.stderr.log"
}

finish() {
  rc=$?
  trap - EXIT
  retrieve || { terminal retrieval_failure "consumer retrieval failed after exit $rc"; exit "$rc"; }
  worker="$artifacts/remote-retrieved/current-vllm-e4m3-h200/CONSUMER_TERMINAL.json"
  state="$artifacts/remote-retrieved/current-vllm-e4m3-h200/CONSUMER_INVOCATION_STATE.json"
  if test -f "$worker"; then
    cp "$worker" "$artifacts/CONSUMER_TERMINAL.json"
    terminal remote_terminal_retrieved "consumer terminal retrieved"
    PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab /root/workspace/research/lab/experiments/gemma4_31b/research_lab release --project gemma4_current_runtime_frontier --condition ready >>"$artifacts/release.log" 2>&1 || true
  else
    terminal retrieval_failure "consumer terminal unavailable after exit $rc"
  fi
  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true
  exit "$rc"
}
trap finish EXIT

heartbeat &
heartbeat_pid=$!
tar -C "$project/inputs" --exclude='./checkpoint' -cf - . | ssh "${ssh_opts[@]}" "glmrunner@$ip" "tar -C $remote/input -xf -" >"$artifacts/input-transfer.stdout.log" 2>"$artifacts/input-transfer.stderr.log"
cat "$project/remote_current_vllm_e4m3_consumer.sh" | ssh "${ssh_opts[@]}" "glmrunner@$ip" "cat > $remote/remote_current_vllm_e4m3_consumer.sh && chmod 700 $remote/remote_current_vllm_e4m3_consumer.sh"
ssh "${ssh_opts[@]}" "glmrunner@$ip" "bash $remote/remote_current_vllm_e4m3_consumer.sh" >"$artifacts/remote.stdout.log" 2>"$artifacts/remote.stderr.log"
