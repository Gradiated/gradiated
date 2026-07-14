#!/usr/bin/env bash
set -Eeuo pipefail

OUT=/workspace/campaign-100-awq-smoke
PUBLIC=/workspace/public-awq
MODEL=/workspace/model-awq
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

root = Path("/workspace/campaign-100-awq-smoke")
rows = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path.name != "manifest.json":
        rows.append({
            "path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
(root / "manifest.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C /workspace -czf "$PUBLIC/awq-smoke.tar.gz.tmp" campaign-100-awq-smoke
  mv "$PUBLIC/awq-smoke.tar.gz.tmp" "$PUBLIC/awq-smoke.tar.gz"
  sha256sum "$PUBLIC/awq-smoke.tar.gz" > "$PUBLIC/awq-smoke.tar.gz.sha256"
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
phase allocation_bootstrap complete

(
  while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
    nvidia-smi --query-gpu=timestamp,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
    sleep 1
  done
) > "$OUT/telemetry.csv" 2> "$OUT/telemetry.stderr.log" &
TELEMETRY=$!

phase model_identity begin
(cd "$MODEL" && sha256sum -c "$MODEL_MANIFEST_PATH") > "$OUT/model-manifest-verification.log" 2>&1
test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00004.safetensors' | wc -l)" -eq 4
test "$(find "$MODEL" -maxdepth 1 -name 'model-*-of-00004.safetensors' -printf '%s\n' | awk '{s+=$1} END {print s}')" = 20170199928
cp "$MODEL/model-files.sha256" "$OUT/model-files.sha256"
du -sb "$MODEL" > "$OUT/model-size.txt"
phase model_identity complete

phase runtime_patch begin
python3 "$PATCHER_PATH" /sgl-workspace/sglang > "$OUT/runtime-patch.json"
timeout 120 python3 - <<'PY' > "$OUT/native-import.json"
import hashlib
import inspect
import json
from pathlib import Path

import sglang
import torch
import transformers
from sglang.srt.layers.quantization.compressed_tensors.schemes.compressed_tensors_wNa16 import CompressedTensorsWNA16
from sglang.srt.layers.quantization.compressed_tensors.schemes.compressed_tensors_wNa16_moe import CompressedTensorsWNA16MoE
from sglang.srt.models.glm4_moe_lite import Glm4MoeLiteForCausalLM

capability = torch.cuda.get_device_capability()
capability_int = capability[0] * 10 + capability[1]
minimum = max(CompressedTensorsWNA16.get_min_capability(), CompressedTensorsWNA16MoE.get_min_capability())
if capability_int < minimum:
    raise SystemExit(f"GPU capability {capability_int} below Marlin minimum {minimum}")
source = Path(inspect.getfile(Glm4MoeLiteForCausalLM))
print(json.dumps({
    "model_class": Glm4MoeLiteForCausalLM.__name__,
    "model_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "sglang": sglang.__version__,
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "transformers": transformers.__version__,
    "gpu_name": torch.cuda.get_device_name(),
    "gpu_compute_capability": capability,
    "marlin_minimum_capability": minimum,
}, indent=2, sort_keys=True))
PY
phase runtime_patch complete

phase checkpoint_metadata_gate begin
python3 - <<'PY' > "$OUT/checkpoint-metadata-gate.json"
import json
from pathlib import Path
from safetensors import safe_open

shard = Path("/workspace/model-awq/model-00001-of-00004.safetensors")
names = {
    "q_shape": "model.layers.1.self_attn.q_a_proj.weight_shape",
    "kv_shape": "model.layers.1.self_attn.kv_a_proj_with_mqa.weight_shape",
    "q_packed": "model.layers.1.self_attn.q_a_proj.weight_packed",
    "kv_packed": "model.layers.1.self_attn.kv_a_proj_with_mqa.weight_packed",
    "q_scale": "model.layers.1.self_attn.q_a_proj.weight_scale",
    "kv_scale": "model.layers.1.self_attn.kv_a_proj_with_mqa.weight_scale",
}
with safe_open(shard, framework="pt", device="cpu") as handle:
    tensors = {key: handle.get_tensor(value) for key, value in names.items()}
if tensors["q_shape"].tolist() != [768, 2048] or tensors["kv_shape"].tolist() != [576, 2048]:
    raise SystemExit("unexpected q/kv weight_shape metadata")
if list(tensors["q_packed"].shape) != [768, 256] or list(tensors["kv_packed"].shape) != [576, 256]:
    raise SystemExit("unexpected packed layout")
if list(tensors["q_scale"].shape) != [768, 64] or list(tensors["kv_scale"].shape) != [576, 64]:
    raise SystemExit("unexpected scale layout")
print(json.dumps({"tensor_names": names, "expected_fused_weight_shape": [1344, 2048]}, indent=2, sort_keys=True))
PY
phase checkpoint_metadata_gate complete

phase model_load begin
CMD=(
  python3 -m sglang.launch_server
  --model-path "$MODEL"
  --served-model-name glm-4.7-flash-awq
  --model-impl sglang
  --quantization compressed-tensors
  --host 127.0.0.1
  --port 30000
  --context-length 4096
  --max-running-requests 1
  --max-total-tokens 4096
  --max-prefill-tokens 4096
  --mem-fraction-static 0.80
  --chunked-prefill-size 4096
  --cuda-graph-backend-decode disabled
  --cuda-graph-backend-prefill disabled
  --disable-radix-cache
  --disable-shared-experts-fusion
  --tool-call-parser glm47
  --reasoning-parser glm45
  --enable-metrics
  --enable-request-time-stats-logging
  --random-seed 1234
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

phase deterministic_completion begin
REQ='{"model":"glm-4.7-flash-awq","messages":[{"role":"user","content":"Return a JSON object with alpha equal to 17 and beta equal to smoke."}],"temperature":0,"max_tokens":64,"seed":20260713,"chat_template_kwargs":{"enable_thinking":false}}'
printf '%s\n' "$REQ" > "$OUT/request.json"
for i in 1 2; do
  curl -fsS --max-time 300 -H 'Content-Type: application/json' -d "$REQ" http://127.0.0.1:30000/v1/chat/completions > "$OUT/response-$i.json"
done
python3 - <<'PY' > "$OUT/determinism.json"
import hashlib
import json
from pathlib import Path
from transformers import AutoTokenizer

root = Path("/workspace/campaign-100-awq-smoke")
responses = [json.loads((root / f"response-{index}.json").read_text()) for index in (1, 2)]
messages = [response["choices"][0]["message"] for response in responses]
normalized = [{key: message.get(key) for key in ("content", "reasoning_content", "tool_calls")} for message in messages]
if normalized[0] != normalized[1]:
    raise SystemExit("greedy response mismatch")
serialized = json.dumps(normalized[0], sort_keys=True, ensure_ascii=False)
tokenizer = AutoTokenizer.from_pretrained("/workspace/model-awq")
print(json.dumps({
    "exact_normalized_identity": True,
    "normalized_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
    "token_ids": tokenizer.encode(serialized, add_special_tokens=False),
    "usage": [response.get("usage") for response in responses],
}, indent=2, sort_keys=True))
PY
curl -fsS http://127.0.0.1:30000/metrics > "$OUT/metrics-after.txt"
python3 - <<'PY' > "$OUT/allocation-result.json"
import json
print(json.dumps({
    "schema_version": 1,
    "model_revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881",
    "model_shards": 4,
    "weight_bytes": 20170199928,
    "full_load_pass": True,
    "deterministic_completion_pass": True,
    "smoke_pass": True,
    "throughput_executed": False,
    "quality_executed": False,
    "experiment_spec_sha256": __import__("os").environ["EXPERIMENT_SPEC_SHA256"],
}, indent=2, sort_keys=True))
PY
phase deterministic_completion complete
