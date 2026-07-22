#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_current_runtime_frontier
artifacts="$project/artifacts/current-vllm-h200-20260722t1231z"
remote=/home/glmrunner/gemma4-current-vllm
ip=195.242.29.186
key=/root/.config/gradiated/providers/gcore/id_ed25519
ssh_opts=(-i "$key" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30)
mkdir -p "$artifacts"
heartbeat_pid=

heartbeat() {
  while true; do
    PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool \
      --lab /root/workspace/research/sol/experiments/gemma4_31b/research_lab \
      heartbeat --project gemma4_current_runtime_frontier \
      >>"$artifacts/heartbeat.log" 2>&1 || true
    sleep 45
  done
}

stop_heartbeat() {
  if test -n "${heartbeat_pid:-}"; then
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
  fi
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
  ssh "${ssh_opts[@]}" "glmrunner@$ip" "test -d $remote/artifacts && tar -C $remote/artifacts -cf - ." | tar -C "$artifacts/remote-retrieved" -xf - >"$artifacts/retrieve.stdout.log" 2>"$artifacts/retrieve.stderr.log" || return 1
}

repair_ready() {
  python3 - "$artifacts/REPAIR_READY.json" "$1" <<'PY'
import json,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); p.write_text(json.dumps({'schema_version':1,'status':'repair_ready','diagnostic':'pre-invocation remote access/retrieval failure','exit_code':int(sys.argv[2]),'repair_deadline_epoch':time.time()+900},indent=2,sort_keys=True)+'\n')
PY
}

finish() {
  rc=$?
  trap - EXIT
  retrieve || true
  worker_terminal="$artifacts/remote-retrieved/current-vllm-h200/WORKER_TERMINAL.json"
  if test -f "$worker_terminal"; then
    cp "$worker_terminal" "$artifacts/WORKER_TERMINAL.json"
    invocation_state="$artifacts/remote-retrieved/current-vllm-h200/INVOCATION_STATE.json"
    if python3 - "$worker_terminal" "$invocation_state" <<'PY'
import json,pathlib,sys
terminal=json.load(open(sys.argv[1]))
state_path=pathlib.Path(sys.argv[2])
state=json.loads(state_path.read_text()) if state_path.exists() else {}
raise SystemExit(0 if terminal.get('classification') in {'integration_failure','startup_timeout'} and not state.get('candidate_science_started') else 1)
PY
    then
      terminal repair_ready "recoverable pre-science worker terminal retrieved"
      repair_ready "$rc"
      stop_heartbeat
      exit "$rc"
    fi
    terminal remote_terminal_retrieved "remote worker terminal retrieved"
    condition=ready
  else
    terminal retrieval_failure "remote worker terminal unavailable after exit $rc"
    repair_ready "$rc"
    stop_heartbeat
    exit "$rc"
  fi
  stop_heartbeat
  PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab /root/workspace/research/sol/experiments/gemma4_31b/research_lab release --project gemma4_current_runtime_frontier --condition "$condition" >>"$artifacts/release.log" 2>&1 || true
  exit "$rc"
}
trap finish EXIT

heartbeat &
heartbeat_pid=$!

ssh "${ssh_opts[@]}" "glmrunner@$ip" "mkdir -p $remote/input $remote/artifacts $remote/checkpoint"
tar -C "$project/inputs" --exclude='./checkpoint' -cf - . | ssh "${ssh_opts[@]}" "glmrunner@$ip" "tar -C $remote/input -xf -" >"$artifacts/input-transfer.stdout.log" 2>"$artifacts/input-transfer.stderr.log"
ssh "${ssh_opts[@]}" "glmrunner@$ip" "cd $remote/checkpoint && test -f model-00001-of-00002.safetensors && test -f model-00002-of-00002.safetensors && printf '%s  %s\\n%s  %s\\n%s  %s\\n' d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2 model.safetensors.index.json e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1 config.json cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f tokenizer.json | sha256sum -c -" >"$artifacts/checkpoint-reuse.stdout.log" 2>"$artifacts/checkpoint-reuse.stderr.log"
cat "$project/remote_current_vllm_h200.sh" | ssh "${ssh_opts[@]}" "glmrunner@$ip" "cat > $remote/remote_current_vllm_h200.sh && chmod 700 $remote/remote_current_vllm_h200.sh"
ssh "${ssh_opts[@]}" "glmrunner@$ip" "cd $remote/checkpoint && sha256sum model.safetensors.index.json config.json tokenizer.json > $remote/artifacts/checkpoint-identity.sha256 && bash $remote/remote_current_vllm_h200.sh" >"$artifacts/remote.stdout.log" 2>"$artifacts/remote.stderr.log"
