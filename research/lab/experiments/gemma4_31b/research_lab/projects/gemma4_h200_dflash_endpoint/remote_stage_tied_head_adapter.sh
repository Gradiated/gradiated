#!/usr/bin/env bash
set -Eeuo pipefail
root=/home/glmrunner/gemma4-dflash/work
source_dir=$root/sglang
models=$root/models
inputs=/home/glmrunner/gemma4-dflash/tied-head-adapter-inputs-20260725
image=gemma4-dflash-sglang:588d1f7bc942
commit=588d1f7bc9424201f89957e145f9d5af633a3eb8
mkdir -p "$root" "$models"
if [[ ! -d "$source_dir/.git" ]]; then git clone https://github.com/sgl-project/sglang.git "$source_dir"; fi
git -C "$source_dir" fetch --depth=1 origin "$commit"
git -C "$source_dir" checkout --detach "$commit"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"
cp "$source_dir/sgl-model-gateway/README.md" "$source_dir/sgl-model-gateway/bindings/python/README.md"
sed -i 's|readme = "../../README.md"|readme = "README.md"|' "$source_dir/sgl-model-gateway/bindings/python/pyproject.toml"
if ! grep -q '^# DFLASH_REPAIR4_OPENAI_DISTRO$' "$source_dir/docker/Dockerfile"; then
  printf '\n# DFLASH_REPAIR4_OPENAI_DISTRO\nRUN python3 -m pip install --no-cache-dir distro==1.9.0\n' >> "$source_dir/docker/Dockerfile"
fi
if ! sudo docker image inspect "$image" >/dev/null 2>&1; then
  sudo docker build --build-arg BRANCH_TYPE=local -f "$source_dir/docker/Dockerfile" -t "$image" "$source_dir"
fi
if [[ ! -f "$models/target/model.safetensors.index.json" || ! -f "$models/draft/config.json" ]]; then
sudo docker run --rm -i -e HF_TOKEN="${HF_TOKEN:-}" -v "$models:/models" "$image" python3 - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("google/gemma-4-31B-it", revision="b9ea41a2887d8607f594846523f94c6cc75ac8a4", local_dir="/models/target")
snapshot_download("z-lab/gemma-4-31B-it-DFlash", revision="eabd648301ce28583cc14757912e5e0f84e152e1", local_dir="/models/draft")
PY
fi
{
  echo '{"schema_version":1,"target_revision":"b9ea41a2887d8607f594846523f94c6cc75ac8a4","draft_revision":"eabd648301ce28583cc14757912e5e0f84e152e1"}'
  git -C "$source_dir" rev-parse HEAD
  sha256sum "$source_dir/python/pyproject.toml" "$source_dir/docker/Dockerfile"
  sudo docker image inspect "$image" --format '{{.Id}}'
  find "$models/target" "$models/draft" -path '*/.cache' -prune -o -type f -print0 | sort -z | xargs -0 sha256sum
} > "$root/RESIDENT_MANIFEST.json"
sha256sum "$root/RESIDENT_MANIFEST.json" > "$root/RESIDENT_MANIFEST.sha256"
printf '%s\n' resident_manifest_persisted > "$root/PHASE.resident_manifest"
exec bash "$inputs/remote_tied_head_adapter.sh"
