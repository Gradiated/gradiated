#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_current_runtime_frontier
artifacts="$project/artifacts/current-sglang-h200-20260722t1557z"
remote=/home/glmrunner/gemma4-current-sglang
ip=89.169.103.149
key=/root/.config/gradiated/providers/gcore/id_ed25519
ssh_opts=(-i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30)
mkdir -p "$artifacts"

heartbeat() {
  while true; do
    PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab /root/workspace/research/sol/experiments/gemma4_31b/research_lab heartbeat --project gemma4_current_runtime_frontier >>"$artifacts/heartbeat.log" 2>&1 || true
    sleep 45
  done
}

terminal() {
  python3 - "$artifacts/OUTER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]);q=p.with_suffix('.part')
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
  retrieve || { terminal retrieval_failure "remote artifacts unavailable after exit $rc"; kill "$heartbeat_pid" 2>/dev/null || true; exit "$rc"; }
  worker="$artifacts/remote-retrieved/current-sglang-c32-r2/WORKER_TERMINAL.json"
  if test -f "$worker"; then
    cp "$worker" "$artifacts/WORKER_TERMINAL.json"
    terminal remote_terminal_retrieved "current SGLang worker terminal retrieved"
    PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab /root/workspace/research/sol/experiments/gemma4_31b/research_lab release --project gemma4_current_runtime_frontier --condition ready >>"$artifacts/release.log" 2>&1 || true
  else
    terminal retrieval_failure "worker terminal absent after exit $rc"
  fi
  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true
  exit "$rc"
}
trap finish EXIT

heartbeat &
heartbeat_pid=$!
ssh "${ssh_opts[@]}" "glmrunner@$ip" "mkdir -p $remote/input $remote/checkpoint $remote/artifacts"
tar -C "$project/inputs" --exclude='./checkpoint' -cf - . | ssh "${ssh_opts[@]}" "glmrunner@$ip" "tar -C $remote/input -xf -" >"$artifacts/input-transfer.stdout.log" 2>"$artifacts/input-transfer.stderr.log"
checkpoint_manifest="$artifacts/checkpoint-manifest.sha256"
prior_manifest="$project/artifacts/current-sglang-h200-20260722t1450z/checkpoint-manifest.sha256"
if test -f "$prior_manifest"; then
  cp "$prior_manifest" "$checkpoint_manifest"
else
  (
    cd "$project/inputs/checkpoint"
    sha256sum chat_template.jinja config.json model-00001-of-00002.safetensors \
      model-00002-of-00002.safetensors model.safetensors.index.json processor_config.json \
      tokenizer.json tokenizer_config.json
  ) >"$checkpoint_manifest"
fi
cat "$checkpoint_manifest" | ssh "${ssh_opts[@]}" "glmrunner@$ip" "cat > $remote/artifacts/checkpoint-manifest.sha256"
while read -r expected name; do
  if ssh "${ssh_opts[@]}" "glmrunner@$ip" \
      "test -f $remote/checkpoint/$name && test \"\$(sha256sum $remote/checkpoint/$name | cut -d' ' -f1)\" = \"$expected\""; then
    continue
  fi
  part="$remote/checkpoint/$name.part.$$"
  scp "${ssh_opts[@]}" "$project/inputs/checkpoint/$name" "glmrunner@$ip:$part"
  ssh "${ssh_opts[@]}" "glmrunner@$ip" \
    "test \"\$(sha256sum $part | cut -d' ' -f1)\" = \"$expected\" && chmod 0444 $part && mv -f $part $remote/checkpoint/$name"
done <"$checkpoint_manifest"
ssh "${ssh_opts[@]}" "glmrunner@$ip" \
  "cd $remote/checkpoint && sha256sum -c $remote/artifacts/checkpoint-manifest.sha256 && chmod 0444 * && cp $remote/artifacts/checkpoint-manifest.sha256 $remote/artifacts/checkpoint-identity.sha256"
cat "$project/remote_current_sglang.sh" | ssh "${ssh_opts[@]}" "glmrunner@$ip" "cat > $remote/remote_current_sglang.sh && chmod 700 $remote/remote_current_sglang.sh"
ssh "${ssh_opts[@]}" "glmrunner@$ip" "bash $remote/remote_current_sglang.sh" >"$artifacts/remote.stdout.log" 2>"$artifacts/remote.stderr.log"
