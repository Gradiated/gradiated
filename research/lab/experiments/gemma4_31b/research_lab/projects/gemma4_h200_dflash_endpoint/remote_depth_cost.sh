#!/usr/bin/env bash
set -Eeuo pipefail
root=/home/glmrunner/gemma4-dflash/work/dflash-depth-cost
models=/home/glmrunner/gemma4-dflash/work/models
project=/home/glmrunner/gemma4-dflash/cycle-project
image=gemma4-dflash-sglang:588d1f7bc942-cycle-oracle
mkdir -p "$root"
for depth in 4 8 12 16; do
  run="$root/depth-$depth"; mkdir -p "$run/oracle"
  install -m 0444 "$project/depth_timing_sitecustomize.py" "$run/oracle/sitecustomize.py"
  sudo docker rm -f gemma4-dflash >/dev/null 2>&1 || true
  sudo docker run -d --name gemma4-dflash --gpus all --ipc=host --network host -e PYTHONPATH=/oracle -e DFLASH_DEPTH="$depth" -e DFLASH_DEPTH_TIMINGS=/work/timings.jsonl -v "$models:/models:ro" -v "$project:/project:ro" -v "$run:/work" -v "$run/oracle:/oracle:ro" "$image" python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --skip-server-warmup --speculative-algorithm DFLASH --speculative-draft-model-path /models/draft --speculative-draft-model-revision eabd648301ce28583cc14757912e5e0f84e152e1 --speculative-num-draft-tokens "$depth" --speculative-draft-attention-backend fa4 > "$run/container-id"
  for i in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models > "$run/models.json" && break; sleep 5; done
  test -s "$run/models.json"
  set +e
  sudo docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py --arm "depth-$depth" --concurrency 32 --output /work/request
  echo "$?" > "$run/runner.exit_code"
  set -e
  sudo docker logs gemma4-dflash > "$run/server.log" 2>&1 || true
  test -s "$run/timings.jsonl"
done
sudo docker rm -f gemma4-dflash >/dev/null
