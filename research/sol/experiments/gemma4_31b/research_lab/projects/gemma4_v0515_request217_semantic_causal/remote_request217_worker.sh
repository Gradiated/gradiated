#!/usr/bin/env bash
set -euo pipefail

root=${REQUEST217_ROOT:?}
out=${REQUEST217_OUT:?}
container=${REQUEST217_CONTAINER:-gemma4-v0515-request217-decode}
image='docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd'
commit='f63458b5beaceabbd9d749b9fc956370e1b649e6'

mkdir -p "$out"
sudo docker ps -a --format '{{json .}}' >"$out/PRE_RESTART_CONTAINERS.jsonl"
for prior in gemma4-ngram-upstream-v0515 "$container"; do
  if sudo docker inspect "$prior" >/dev/null 2>&1; then
    configured=$(sudo docker inspect --format '{{.Config.Image}}' "$prior")
    case "$configured" in
      *ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd*) ;;
      *) echo "unexpected_prior_container_image:$prior:$configured" >&2; exit 41 ;;
    esac
    sudo docker rm -f "$prior"
  fi
done

mapfile -t args < <(python3 - <<'PY'
import json, os
for arg in json.load(open(os.path.join(os.environ['REQUEST217_ROOT'], 'inputs', 'decode_attention_launch.json')))['args']:
    print(arg)
PY
)
sudo docker run -d --rm --name "$container" \
  --label "org.opencontainers.image.revision=$commit" \
  --gpus all --network host --ipc host --shm-size 16g \
  -v /home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint:/work/checkpoint:ro \
  "$image" python3 -m sglang.launch_server "${args[@]}" >"$out/CONTAINER_ID.txt"

exec env REQUEST217_ROOT="$root" REQUEST217_OUT="$out" REQUEST217_CONTAINER="$container" \
  python3 "$root/remote_request217_discriminator.py"
