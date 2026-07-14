#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/campaign-100-vllm-awq-batch
PUBLIC=/workspace/public-vllm-awq-batch
MODEL=/workspace/model-awq
TOKENIZER=/input/tokenizer
QUALITY=/input/quality
VLLM_DTYPE="${VLLM_DTYPE:-bfloat16}"
VLLM_MAX_NUM_BATCHED_TOKENS="${VLLM_MAX_NUM_BATCHED_TOKENS:-32768}"
VLLM_DECODE_BLOCK_N="${VLLM_DECODE_BLOCK_N:-32}"
VLLM_DECODE_NUM_STAGES="${VLLM_DECODE_NUM_STAGES:-2}"
VLLM_NUM_KV_SPLITS="${VLLM_NUM_KV_SPLITS:-4}"
SERVER=
TELEMETRY=

rm -rf "$OUT" "$PUBLIC"
mkdir -p "$OUT" "$PUBLIC"

phase() {
  printf '{"timestamp":"%s","phase":"%s","state":"%s"}\n' "$(date -u +%FT%TZ)" "$1" "$2" >> "$OUT/phases.jsonl"
}

package_artifact() {
  python3 - <<'PY'
import hashlib
import json
from pathlib import Path
root = Path("/workspace/campaign-100-vllm-awq-batch")
rows = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path.name != "manifest.json":
        rows.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
(root / "manifest.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C /workspace -czf "$PUBLIC/vllm-awq-batch.tar.gz.tmp" campaign-100-vllm-awq-batch
  mv "$PUBLIC/vllm-awq-batch.tar.gz.tmp" "$PUBLIC/vllm-awq-batch.tar.gz"
  sha256sum "$PUBLIC/vllm-awq-batch.tar.gz" > "$PUBLIC/vllm-awq-batch.tar.gz.sha256"
}

finish() {
  rc=$?
  set +e
  phase teardown begin
  [ -n "$SERVER" ] && kill -TERM "$SERVER" 2>/dev/null
  [ -n "$TELEMETRY" ] && kill -TERM "$TELEMETRY" 2>/dev/null
  [ -n "$SERVER" ] && wait "$SERVER" 2>/dev/null
  [ -n "$TELEMETRY" ] && wait "$TELEMETRY" 2>/dev/null
  nvidia-smi -q > "$OUT/nvidia-smi-final.txt" 2>&1
  phase teardown complete
  package_artifact
  exit "$rc"
}
trap finish EXIT

phase allocation_bootstrap begin
uname -a > "$OUT/uname.txt"
nvidia-smi -q > "$OUT/nvidia-smi-initial.txt" 2>&1
python3 -m pip freeze > "$OUT/pip-freeze.txt"
python3 - <<'PY' > "$OUT/native-import.json"
import json
import torch
import transformers
import vllm
print(json.dumps({"vllm": vllm.__version__, "torch": torch.__version__, "cuda": torch.version.cuda, "transformers": transformers.__version__, "gpu": torch.cuda.get_device_name(), "capability": torch.cuda.get_device_capability()}, indent=2, sort_keys=True))
PY
phase allocation_bootstrap complete

python3 /input/vllm_decode_kernel_patch.py --block-n "$VLLM_DECODE_BLOCK_N" --num-stages "$VLLM_DECODE_NUM_STAGES" --num-kv-splits "$VLLM_NUM_KV_SPLITS" --evidence "$OUT/vllm-decode-kernel-patch.json"

(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" &
TELEMETRY=$!

phase model_identity begin
MARKER="$MODEL/.campaign-integrity-v1"
MANIFEST_SHA="$(sha256sum "$MODEL_MANIFEST_PATH" | awk '{print $1}')"
METADATA_SHA="$(find "$MODEL" -maxdepth 1 -type f ! -name '.campaign-integrity-v1' -printf '%f %s %T@\n' | sort | sha256sum | awk '{print $1}')"
if [ -f "$MARKER" ] && grep -qx "manifest_sha256=$MANIFEST_SHA" "$MARKER" && grep -qx "metadata_sha256=$METADATA_SHA" "$MARKER"; then
  printf 'reused content-addressed full-verification marker\n' > "$OUT/model-manifest-verification.log"
  printf 'marker_reused=true\n' >> "$OUT/model-manifest-verification.log"
else
  (cd "$MODEL" && sha256sum -c "$MODEL_MANIFEST_PATH") > "$OUT/model-manifest-verification.log" 2>&1
  printf 'manifest_sha256=%s\nmetadata_sha256=%s\n' "$MANIFEST_SHA" "$METADATA_SHA" > "$MARKER"
  printf 'marker_reused=false\n' >> "$OUT/model-manifest-verification.log"
fi
test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00004.safetensors' | wc -l)" -eq 4
test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00004.safetensors' -printf '%s\n' | awk '{s+=$1} END {printf "%.0f\n",s}')" = 20170199928
cp "$MODEL/model-files.sha256" "$OUT/model-files.sha256"
cp "$MARKER" "$OUT/model-integrity-marker.txt"
du -sb "$MODEL" > "$OUT/model-size.txt"
test "$(python3 "$QUALITY/validate_quality.py")" = 152548d51fba8e8ff5e8f1e665c5af166fb6d97cdf3010723042112855964668
sha256sum "$TOKENIZER/tokenizer.json" "$TOKENIZER/tokenizer_config.json" "$TOKENIZER/chat_template.jinja" > "$OUT/tokenizer-hashes.sha256"
grep -q '^19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d ' "$OUT/tokenizer-hashes.sha256"
grep -q '^31a173e2797ddc8b72ac996803513e627fc28d7aad02cfcce321a431d865c86d ' "$OUT/tokenizer-hashes.sha256"
grep -q '^d63ad536c3c81880043e22ec7fd08db42b4d8fb7c89c7138bc562bfa25281375 ' "$OUT/tokenizer-hashes.sha256"
phase model_identity complete

phase model_load begin
export VLLM_TORCH_PROFILER_DIR="$OUT/profiler"
CMD=(
  vllm serve "$MODEL"
  --tokenizer "$TOKENIZER"
  --served-model-name glm-4.7-flash-awq
  --host 127.0.0.1
  --port 30000
  --max-model-len 32768
  --max-num-seqs 8
  --max-num-batched-tokens "$VLLM_MAX_NUM_BATCHED_TOKENS"
  --gpu-memory-utilization 0.90
  --no-enable-prefix-caching
  --quantization compressed-tensors
  --dtype "$VLLM_DTYPE"
  --generation-config vllm
  --enable-auto-tool-choice
  --tool-call-parser glm47
  --reasoning-parser glm45
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"/workspace/campaign-100-vllm-awq-batch/profiler","torch_profiler_with_stack":false,"torch_profiler_record_shapes":true,"torch_profiler_with_memory":false,"torch_profiler_use_gzip":true,"ignore_frontend":true,"max_iterations":256}'
  --seed 1234
)
printf '%q ' "${CMD[@]}" > "$OUT/server-command.txt"
"${CMD[@]}" > "$OUT/server.stdout.log" 2> "$OUT/server.stderr.log" &
SERVER=$!
healthy=0
for _ in $(seq 1 900); do
  if ! kill -0 "$SERVER" 2>/dev/null; then
    wait "$SERVER"
    exit $?
  fi
  if curl -fsS http://127.0.0.1:30000/health >/dev/null; then
    healthy=1
    break
  fi
  if [ "$(date +%s)" -ge "$CAMPAIGN_DEADLINE_EPOCH" ]; then
    break
  fi
  sleep 2
done
test "$healthy" -eq 1
nvidia-smi -q > "$OUT/nvidia-smi-loaded.txt" 2>&1
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-before.txt"
phase model_load complete

phase conditional_semantic_quality_performance_batch begin
set +e
python3 /input/vllm_batched_runner.py \
  --output "$OUT" \
  --tokenizer "$TOKENIZER" \
  --quality "$QUALITY" \
  --bf16-responses /input/bf16-control-responses.jsonl \
  > "$OUT/batch-runner.stdout.log" 2> "$OUT/batch-runner.stderr.log"
RUNNER_RC=$?
set -e
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-after.txt"
if [ -s "$OUT/allocation-result.json" ]; then
python3 - <<'PY'
import json
import os
from pathlib import Path
path = Path("/workspace/campaign-100-vllm-awq-batch/allocation-result.json")
value = json.loads(path.read_text())
value.update({"runtime": "vllm-0.15.0", "dtype": os.environ["VLLM_DTYPE"], "max_num_batched_tokens": int(os.environ["VLLM_MAX_NUM_BATCHED_TOKENS"]), "decode_grouped_block_n": int(os.environ["VLLM_DECODE_BLOCK_N"]), "decode_grouped_num_stages": int(os.environ["VLLM_DECODE_NUM_STAGES"]), "num_kv_splits": int(os.environ["VLLM_NUM_KV_SPLITS"]), "model_revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881", "full_load_pass": True, "experiment_spec_sha256": os.environ["EXPERIMENT_SPEC_SHA256"]})
path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY
fi
phase conditional_semantic_quality_performance_batch complete
exit "$RUNNER_RC"
