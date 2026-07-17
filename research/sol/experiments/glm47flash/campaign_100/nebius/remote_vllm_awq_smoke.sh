#!/usr/bin/env bash
set -Eeuo pipefail

VLLM_SCIENTIFIC_MODE="${VLLM_SCIENTIFIC_MODE:-awq}"
if [ "$VLLM_SCIENTIFIC_MODE" = "bf16-v2-quality" ]; then
  OUT=/workspace/bf16-v2-quality
  PUBLIC=/workspace/public-bf16-v2-quality
  MODEL=/workspace/model-bf16
  MODEL_NAME=glm-4.7-flash-bf16
  V2=/input/v2
else
  OUT=/workspace/campaign-100-vllm-awq-batch
  PUBLIC=/workspace/public-vllm-awq-batch
  MODEL=/workspace/model-awq
  MODEL_NAME=glm-4.7-flash-awq
fi
export OUT PUBLIC
TOKENIZER=/input/tokenizer
QUALITY=/input/quality
VLLM_DTYPE="${VLLM_DTYPE:-bfloat16}"
VLLM_MAX_NUM_BATCHED_TOKENS="${VLLM_MAX_NUM_BATCHED_TOKENS:-32768}"
VLLM_MAX_NUM_SEQS="${VLLM_MAX_NUM_SEQS:-8}"
VLLM_FRONTIER_CONCURRENCIES="${VLLM_FRONTIER_CONCURRENCIES:-1,8}"
VLLM_DECODE_BLOCK_N="${VLLM_DECODE_BLOCK_N:-32}"
VLLM_DECODE_NUM_STAGES="${VLLM_DECODE_NUM_STAGES:-2}"
VLLM_NUM_KV_SPLITS="${VLLM_NUM_KV_SPLITS:-4}"
VLLM_KV_CACHE_DTYPE="${VLLM_KV_CACHE_DTYPE:-auto}"
VLLM_NATIVE_MTP="${VLLM_NATIVE_MTP:-0}"
VLLM_EXIT35_MODE="${VLLM_EXIT35_MODE:-0}"
VLLM_NGRAM_PROMPT_LOOKUP="${VLLM_NGRAM_PROMPT_LOOKUP:-0}"
VLLM_RUN_METHODOLOGY="${VLLM_RUN_METHODOLOGY:-0}"
VLLM_EXIT35_PREFILL_THRESHOLD="${VLLM_EXIT35_PREFILL_THRESHOLD:-64}"
VLLM_SERVER_HEALTH_TIMEOUT_SECONDS="${VLLM_SERVER_HEALTH_TIMEOUT_SECONDS:-360}"
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
import os
from pathlib import Path
root = Path(os.environ["OUT"])
rows = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path.name != "manifest.json":
        rows.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
(root / "manifest.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C "$(dirname "$OUT")" -czf "$PUBLIC/vllm-awq-batch.tar.gz.tmp" "$(basename "$OUT")"
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

if [ "$VLLM_SCIENTIFIC_MODE" = "awq" ]; then
  if [ "${GLM_HEAD_SHARED_W4:-0}" = "1" ]; then
    python3 /input/official_head_shared_w4_bind.py
    python3 /input/official_head_shared_w4_cuda_oracle.py > "$OUT/official-head-shared-w4-cuda-oracle.json"
  fi
  python3 /input/vllm_decode_kernel_patch.py --block-n "$VLLM_DECODE_BLOCK_N" --num-stages "$VLLM_DECODE_NUM_STAGES" --num-kv-splits "$VLLM_NUM_KV_SPLITS" --evidence "$OUT/vllm-decode-kernel-patch.json"
  if [ "$VLLM_EXIT35_MODE" = "1" ]; then
    python3 /input/exit35_vllm_source_patch.py \
      --source /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/glm4_moe_lite.py \
      --evidence "$OUT/exit35-vllm-source-patch.json"
  fi
  if [ "${GLM_MOE_TOP2_NO_SHARED:-0}" = "1" ]; then
    python3 /input/moe_top2_no_shared_patch.py --source-root /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models --evidence "$OUT/moe-top2-no-shared-patch.json"
  fi
fi

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
if [ "$VLLM_SCIENTIFIC_MODE" = "awq" ]; then
  python3 - <<'PY' > "$OUT/derived-manifest-contract.json"
import hashlib
import json
from pathlib import Path
root = Path("/workspace/model-awq")
manifest_path = root / "model-files-manifest.json"
manifest = json.loads(manifest_path.read_text())
repository = manifest.get("repository")
derived = repository == "local-derived/glm47flash-student39"
minimal_depth42_v2 = repository == "local-derived/glm47flash-minimal-depth42-v2"
minimal_depth43_v2 = repository == "local-derived/glm47flash-minimal-depth43-v2"
expected = {
    "student39": {
        "manifest_sha256": "d09c1b7dbd10c91eec8aba98fc3f14878bf8d1784d610499935c3e355ba9e86a",
        "config_sha256": "07b92832975cb7d174660e88127e91b6269605fe0cfb1bd9bfd282056969be54",
        "index_sha256": "407b00ffcfa0a69174d4d65473f3fd889ccc9cadb88a75d98393ff2034d8153e",
        "weight_bytes": 15544868264,
    },
    "student42": {
        "manifest_sha256": "a41e353015487ff58d367bf5ce42ae7c7d49de87c339c49deab714a69a42a584",
        "config_sha256": "3859511a5a451f8d9a5fd0dd10e25edd98dd40cc4e970d4a124047dc86982899",
        "index_sha256": "8758d9236670cb1c0f693ce6b54f7a9318c85c76feb8b333b8e0429a0113edde",
        "weight_bytes": 16658558680,
    },
}
if derived or minimal_depth42_v2 or minimal_depth43_v2:
    rows = {row["path"]: row for row in manifest["files"]}
    observed = {"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "config_sha256": rows["config.json"]["sha256"], "index_sha256": rows["model.safetensors.index.json"]["sha256"], "weight_bytes": manifest["weight_bytes"]}
    if minimal_depth42_v2:
        expected_minimal = {"manifest_sha256": "cfee71f350b69a931bc6700712db9850780c30f2e8aa51a406ce9ac7a668cdda", "config_sha256": "3859511a5a451f8d9a5fd0dd10e25edd98dd40cc4e970d4a124047dc86982899", "index_sha256": "8758d9236670cb1c0f693ce6b54f7a9318c85c76feb8b333b8e0429a0113edde", "weight_bytes": 16658558680}
        checksum_sha = hashlib.sha256((root / "model-files.sha256").read_bytes()).hexdigest()
        if observed != expected_minimal or checksum_sha != "87d080fa3b10a184abf39e050f6dd67264b32394b43d45caecd93d32e3512950":
            raise SystemExit(f"minimal depth42 v2 manifest contract mismatch: {observed}")
        derived_identity = "minimal-depth42-v2"
    elif minimal_depth43_v2:
        expected_minimal = {"manifest_sha256": "745fdda3cd7c4ef43ad4a88cb10a05628e1887085528419bf7a004af80b47741", "config_sha256": "a400acbe6b5322ba4ad2ef14e3892105bc516bd802584e60775b492b5ca68e7c", "index_sha256": "fb7aaed29073ab00a662526aab18e977de284b88533c777db7ea039b4c76764d", "weight_bytes": 17029788816}
        checksum_sha = hashlib.sha256((root / "model-files.sha256").read_bytes()).hexdigest()
        if observed != expected_minimal or checksum_sha != "87e5f71388c1cd5293e13681641a0575136930e360bdbd52db0cc59ba5a045eb":
            raise SystemExit(f"minimal depth43 v2 manifest contract mismatch: {observed}")
        derived_identity = "minimal-depth43-v2"
    else:
        derived_identity = next((name for name, identity in expected.items() if observed == identity), None)
    if derived_identity is None:
        raise SystemExit(f"derived manifest contract mismatch: {observed}")
else:
    observed = {"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "weight_bytes": manifest["weight_bytes"]}
print(json.dumps({"derived_student": derived, "minimal_depth42_v2": minimal_depth42_v2, "minimal_depth43_v2": minimal_depth43_v2, "derived_identity": derived_identity if derived or minimal_depth42_v2 or minimal_depth43_v2 else None, **observed}, sort_keys=True))
PY
  EXPECTED_WEIGHT_BYTES="$(python3 -c 'import json; print(json.load(open("/workspace/model-awq/model-files-manifest.json"))["weight_bytes"])')"
  test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00004.safetensors' | wc -l)" -eq 4
  test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00004.safetensors' -printf '%s\n' | awk '{s+=$1} END {printf "%.0f\n",s}')" = "$EXPECTED_WEIGHT_BYTES"
else
  test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00048.safetensors' | wc -l)" -eq 48
  test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00048.safetensors' -printf '%s\n' | awk '{s+=$1} END {printf "%.0f\n",s}')" = 62444175504
fi
cp "$MODEL/model-files.sha256" "$OUT/model-files.sha256"
cp "$MARKER" "$OUT/model-integrity-marker.txt"
du -sb "$MODEL" > "$OUT/model-size.txt"
if [ "$VLLM_SCIENTIFIC_MODE" = "awq" ]; then
  test "$(python3 "$QUALITY/validate_quality.py")" = 152548d51fba8e8ff5e8f1e665c5af166fb6d97cdf3010723042112855964668
fi
sha256sum "$TOKENIZER/tokenizer.json" "$TOKENIZER/tokenizer_config.json" "$TOKENIZER/chat_template.jinja" > "$OUT/tokenizer-hashes.sha256"
if [ "$VLLM_SCIENTIFIC_MODE" = "awq" ]; then
  grep -q '^353a3ff93723c098ac93fb593d4d1b93faede916fe502b005cd503871023e012 ' "$OUT/tokenizer-hashes.sha256"
  grep -q '^b6b807f7bfaf4fb4bd3952f58a70d61442620df8e5d8a904dcf4bc6ca7946940 ' "$OUT/tokenizer-hashes.sha256"
  grep -q '^d63ad536c3c81880043e22ec7fd08db42b4d8fb7c89c7138bc562bfa25281375 ' "$OUT/tokenizer-hashes.sha256"
fi
phase model_identity complete

phase model_load begin
export VLLM_TORCH_PROFILER_DIR="$OUT/profiler"
CMD=(
  vllm serve "$MODEL"
  --tokenizer "$TOKENIZER"
  --served-model-name "$MODEL_NAME"
  --host 127.0.0.1
  --port 30000
  --max-model-len "$VLLM_MAX_MODEL_LEN"
  --max-num-seqs "$VLLM_MAX_NUM_SEQS"
  --max-num-batched-tokens "$VLLM_MAX_NUM_BATCHED_TOKENS"
  --gpu-memory-utilization 0.90
  --no-enable-prefix-caching
  --dtype "$VLLM_DTYPE"
  --generation-config vllm
  --enable-auto-tool-choice
  --tool-call-parser glm47
  --reasoning-parser glm45
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"/workspace/campaign-100-vllm-awq-batch/profiler","torch_profiler_with_stack":false,"torch_profiler_record_shapes":true,"torch_profiler_with_memory":false,"torch_profiler_use_gzip":true,"ignore_frontend":true,"max_iterations":256}'
  --seed 1234
)
if [ "$VLLM_SCIENTIFIC_MODE" = "awq" ]; then
  CMD+=(--quantization compressed-tensors)
  if [ "$VLLM_NATIVE_MTP" = "1" ]; then
    CMD+=(--speculative-config '{"method":"glm4_moe_lite_mtp","num_speculative_tokens":1}')
  fi
  if [ "$VLLM_NGRAM_PROMPT_LOOKUP" = "1" ]; then
    CMD+=(--speculative-config '{"method":"ngram","num_speculative_tokens":5,"prompt_lookup_min":5,"prompt_lookup_max":5}')
  fi
else
  CMD+=(--enforce-eager)
fi
if [ "$VLLM_KV_CACHE_DTYPE" != "auto" ]; then
  CMD+=(--kv-cache-dtype "$VLLM_KV_CACHE_DTYPE")
fi
printf '%q ' "${CMD[@]}" > "$OUT/server-command.txt"
"${CMD[@]}" > "$OUT/server.stdout.log" 2> "$OUT/server.stderr.log" &
SERVER=$!
healthy=0
for _ in $(seq 1 "$VLLM_SERVER_HEALTH_TIMEOUT_SECONDS"); do
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

if [ "$VLLM_SCIENTIFIC_MODE" = "bf16-v2-quality" ]; then
  phase v2_quality_captures begin
  for phase_id in 1 2 3; do
    if [ "$phase_id" -gt 1 ]; then
      kill -TERM "$SERVER" 2>/dev/null || true
      wait "$SERVER" 2>/dev/null || true
      SERVER=
      "${CMD[@]}" > "$OUT/server-${phase_id}.stdout.log" 2> "$OUT/server-${phase_id}.stderr.log" &
      SERVER=$!
      healthy=0
      for _ in $(seq 1 900); do
        if curl -fsS http://127.0.0.1:30000/health >/dev/null; then healthy=1; break; fi
        sleep 2
      done
      test "$healthy" -eq 1
    fi
    python3 /input/vllm_v2_quality_runner.py --suite "$V2/development.jsonl" --output "$OUT/capture-$phase_id" --revision "$MODEL_REVISION" --suite-sha256 "4953e524526106b353a7df8de6d84e45fa18d96464935117ca926f483d03a6b7"
    test "$(find "$OUT/capture-$phase_id" -maxdepth 1 -type f | wc -l)" -ge 7
  done
  phase v2_quality_captures complete
  exit 0
fi

phase conditional_semantic_quality_performance_batch begin
set +e
python3 /input/vllm_batched_runner.py \
  --output "$OUT" \
  --tokenizer "$TOKENIZER" \
  --quality "$QUALITY" \
  --bf16-responses /input/bf16-control-responses.jsonl \
  --concurrencies "$VLLM_FRONTIER_CONCURRENCIES" \
  > "$OUT/batch-runner.stdout.log" 2> "$OUT/batch-runner.stderr.log"
RUNNER_RC=$?
set -e
METHODOLOGY_RC=0
if [ "$VLLM_RUN_METHODOLOGY" = "1" ]; then
  set +e
  python3 /input/vllm_methodology_runner.py --output "$OUT" > "$OUT/aa-methodology.stdout.log" 2> "$OUT/aa-methodology.stderr.log"
  METHODOLOGY_RC=$?
  set -e
fi
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-after.txt"
if [ -s "$OUT/allocation-result.json" ]; then
python3 - <<'PY'
import json
import os
from pathlib import Path
path = Path("/workspace/campaign-100-vllm-awq-batch/allocation-result.json")
value = json.loads(path.read_text())
model_manifest = json.loads(Path("/workspace/model-awq/model-files-manifest.json").read_text())
value.update({"runtime": "vllm-0.15.0", "dtype": os.environ["VLLM_DTYPE"], "kv_cache_dtype_requested": os.environ.get("VLLM_KV_CACHE_DTYPE", "auto"), "max_num_batched_tokens": int(os.environ["VLLM_MAX_NUM_BATCHED_TOKENS"]), "max_num_seqs": int(os.environ["VLLM_MAX_NUM_SEQS"]), "frontier_concurrencies": [int(value) for value in os.environ["VLLM_FRONTIER_CONCURRENCIES"].split(",")], "decode_grouped_block_n": int(os.environ["VLLM_DECODE_BLOCK_N"]), "decode_grouped_num_stages": int(os.environ["VLLM_DECODE_NUM_STAGES"]), "num_kv_splits": int(os.environ["VLLM_NUM_KV_SPLITS"]), "model_revision": model_manifest["revision"], "weight_bytes": model_manifest["weight_bytes"], "full_load_pass": True, "experiment_spec_sha256": os.environ["EXPERIMENT_SPEC_SHA256"], "ngram_prompt_lookup": os.environ.get("VLLM_NGRAM_PROMPT_LOOKUP") == "1", "ngram_speculative_config": {"method": "ngram", "num_speculative_tokens": 5, "prompt_lookup_min": 5, "prompt_lookup_max": 5} if os.environ.get("VLLM_NGRAM_PROMPT_LOOKUP") == "1" else None, "moe_top2_no_shared": os.environ.get("GLM_MOE_TOP2_NO_SHARED") == "1", "moe_top2_no_shared_patch_sha256": os.environ.get("GLM_MOE_TOP2_NO_SHARED_PATCH_SHA256") or None})
path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY
fi
phase conditional_semantic_quality_performance_batch complete
if [ "$METHODOLOGY_RC" -ne 0 ]; then
  exit "$METHODOLOGY_RC"
fi
exit "$RUNNER_RC"
