#!/usr/bin/env bash
set -Eeuo pipefail
root=/home/glmrunner/gemma4-dflash/work/dflash-depth4-endpoint
models=/home/glmrunner/gemma4-dflash/work/models
project=/home/glmrunner/gemma4-dflash/depth4-endpoint-project
image=gemma4-dflash-sglang:588d1f7bc942-cycle-oracle
mkdir -p "$root/results"
cleanup() { sudo docker rm -f gemma4-dflash >/dev/null 2>&1 || true; }
trap cleanup EXIT
start() {
  local arm=$1; shift
  cleanup
  sudo docker run -d --name gemma4-dflash --gpus all --ipc=host --network host -v "$models:/models:ro" -v "$project:/project:ro" -v "$root:/work" "$image" python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --skip-server-warmup "$@" > "$root/$arm.container"
  for _ in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models > "$root/$arm.models.json" && return; sleep 2; done
  sudo docker logs gemma4-dflash > "$root/$arm.server.log" 2>&1 || true
  return 1
}
start ar
sudo docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py --arm ar-c32 --concurrency 32 --output /work/results/ar-c32
sudo docker logs gemma4-dflash > "$root/ar.server.log" 2>&1
start dflash --speculative-algorithm DFLASH --speculative-draft-model-path /models/draft --speculative-draft-model-revision eabd648301ce28583cc14757912e5e0f84e152e1 --speculative-num-draft-tokens 4 --speculative-draft-attention-backend fa4
sudo docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py --arm dflash-depth4-c32 --concurrency 32 --output /work/results/dflash-depth4-c32
sudo docker logs gemma4-dflash > "$root/dflash.server.log" 2>&1
grep -E 'accept len|DFLASH verify completed' "$root/dflash.server.log" > "$root/dflash.accepted-prefix.log" || true
cleanup
trap - EXIT
