#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-dflash/work
source_dir="$root/sglang"
models="$root/models"
image=gemma4-dflash-sglang:588d1f7bc942
commit=588d1f7bc9424201f89957e145f9d5af633a3eb8
target_revision=b9ea41a2887d8607f594846523f94c6cc75ac8a4
draft_revision=eabd648301ce28583cc14757912e5e0f84e152e1
project=/home/glmrunner/gemma4-dflash/project

docker() { sudo docker "$@"; }

mkdir -p "$root" "$models" "$root/results"
if [[ ! -d "$source_dir/.git" ]]; then git clone https://github.com/sgl-project/sglang.git "$source_dir"; fi
git -C "$source_dir" fetch --depth=1 origin "$commit"
git -C "$source_dir" checkout --detach "$commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
test "$(sha256sum "$source_dir/python/pyproject.toml" | awk '{print $1}')" = 6b40552b99409cf95cc5f2341786e2732c9d6b7db2d220ecd57fd95441b412ac
cp "$source_dir/sgl-model-gateway/README.md" "$source_dir/sgl-model-gateway/bindings/python/README.md"
sed -i 's|readme = "../../README.md"|readme = "README.md"|' "$source_dir/sgl-model-gateway/bindings/python/pyproject.toml"
# The local editable SGLang install uses --no-deps after the gateway wheel
# reinstall.  Its OpenAI 2.6.1 dependency needs distro at server import time.
# Keep the upstream source commit intact; append this pinned image-only repair.
if ! grep -q '^# DFLASH_REPAIR4_OPENAI_DISTRO$' "$source_dir/docker/Dockerfile"; then
  printf '\n# DFLASH_REPAIR4_OPENAI_DISTRO\nRUN python3 -m pip install --no-cache-dir distro==1.9.0\n' >> "$source_dir/docker/Dockerfile"
fi
docker build --build-arg BRANCH_TYPE=local -f "$source_dir/docker/Dockerfile" -t "$image" "$source_dir"
docker image inspect "$image" --format '{{.Id}}' > "$root/IMAGE_ID.txt"

stage_models() {
  # Keep stdin attached: Python otherwise receives an empty heredoc and exits
  # successfully without materializing either immutable revision.
  docker run --rm -i -e HF_TOKEN="${HF_TOKEN:-}" -v "$models:/models" "$image" python3 - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("google/gemma-4-31B-it", revision="b9ea41a2887d8607f594846523f94c6cc75ac8a4", local_dir="/models/target")
snapshot_download("z-lab/gemma-4-31B-it-DFlash", revision="eabd648301ce28583cc14757912e5e0f84e152e1", local_dir="/models/draft")
PY
}

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

stage_models
start_server ar
docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py --arm ar-diagnostic --concurrency 4 --output /work/dflash/results/ar-diagnostic
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
