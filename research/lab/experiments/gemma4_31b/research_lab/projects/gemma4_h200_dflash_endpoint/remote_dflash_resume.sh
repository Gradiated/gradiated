#!/usr/bin/env bash
# Resume after AR model load succeeded but the first consumer found an empty
# project mount.  Do not restart that loaded AR producer.
set -Eeuo pipefail

root=/home/glmrunner/gemma4-dflash/work
models="$root/models"
project=/home/glmrunner/gemma4-dflash/project
image=gemma4-dflash-sglang:588d1f7bc942
target_revision=b9ea41a2887d8607f594846523f94c6cc75ac8a4
draft_revision=eabd648301ce28583cc14757912e5e0f84e152e1
docker() { sudo docker "$@"; }

start_server() {
  local arm=$1
  docker rm -f gemma4-dflash >/dev/null 2>&1 || true
  local flags=(--model-path /models/target --tokenizer-path /models/target --revision "$target_revision" --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup)
  if [[ "$arm" = dflash ]]; then flags+=(--speculative-algorithm DFLASH --speculative-draft-model-path /models/draft --speculative-draft-model-revision "$draft_revision" --speculative-num-draft-tokens 16 --speculative-draft-attention-backend fa4); fi
  docker run -d --name gemma4-dflash --gpus all --ipc=host --network host -v "$models:/models:ro" -v "$project:/project:ro" -v "$root:/work/dflash" "$image" python3 -m sglang.launch_server "${flags[@]}"
  for _ in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models > "$root/${arm}-models.json" && return; sleep 5; done
  docker logs gemma4-dflash > "$root/${arm}-server.log" 2>&1 || true
  return 1
}

# The resident AR server is the persisted producer. Its project mount is
# immutable, so copy only the hash-bound runner to the writable work mount.
install -m 0444 "$project/dflash_endpoint_runner.py" "$root/dflash_endpoint_runner.py"
sha256sum "$root/dflash_endpoint_runner.py" > "$root/RUNNER.resume.sha256"
docker exec gemma4-dflash python3 /work/dflash/dflash_endpoint_runner.py --arm ar-diagnostic --concurrency 4 --output /work/dflash/results/ar-diagnostic
docker logs gemma4-dflash > "$root/ar-server.log" 2>&1
start_server dflash
docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py --arm dflash-diagnostic --concurrency 4 --output /work/dflash/results/dflash-diagnostic
docker logs gemma4-dflash > "$root/dflash-server.log" 2>&1
grep -q 'Initialized DFLASH draft runner' "$root/dflash-server.log"
grep -q 'DFLASH verify completed' "$root/dflash-server.log"
start_server ar
docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py --arm ar-c32 --concurrency 32 --output /work/dflash/results/ar-c32
docker logs gemma4-dflash > "$root/ar-c32-server.log" 2>&1
start_server dflash
docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py --arm dflash-c32 --concurrency 32 --output /work/dflash/results/dflash-c32
docker logs gemma4-dflash > "$root/dflash-c32-server.log" 2>&1
python3 "$project/reconcile_dflash.py" --results "$root/results" --output "$root/FINAL_TERMINAL.json"
