#!/usr/bin/env bash
set -Eeuo pipefail

packet=$1
root=$2
runner=$3
image=gemma4-dflash-sglang:588d1f7bc942-cycle-oracle
models=/home/glmrunner/gemma4-dflash/work/models
container=gemma4-request25-boundary
source_binding=cc49aa4192e737c90ddd5871c59efd4fc854c6a0ca094c557a0e78545bdb8c52
stage=preflight
science_started=false

mkdir -p "$root/observer"

finish() {
  rc=$?
  sudo -n docker logs "$container" > "$root/server.log" 2>&1 || true
  sudo -n docker inspect "$container" > "$root/container.json" 2>&1 || true
  sudo -n docker rm -f "$container" > "$root/container-stop.log" 2>&1 || true
  python3 - "$root/REMOTE_TERMINAL.json" "$stage" "$rc" "$science_started" <<'PY'
import datetime
import json
import pathlib
import sys

pathlib.Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "recorded_at_utc": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
            "stage": sys.argv[2],
            "exit_code": int(sys.argv[3]),
            "science_started": sys.argv[4] == "true",
        },
        sort_keys=True,
    )
    + "\n"
)
PY
}
trap finish EXIT

sudo -n docker version > "$root/docker-version.txt"
install -m 0444 "$packet/observer/request25_boundary_probe_sitecustomize.py" "$root/observer/sitecustomize.py"
install -m 0444 "$packet/observer/request25_boundary_probe.py" "$root/observer/request25_boundary_probe.py"
install -m 0444 "$packet/observer/request25_payload_adapter.py" "$root/observer/request25_payload_adapter.py"

stage=source-identity
sudo -n docker run --rm "$image" sha256sum \
  /sgl-workspace/sglang/python/sglang/srt/speculative/dflash_info.py \
  /sgl-workspace/sglang/python/sglang/srt/speculative/dflash_info_v2.py \
  /sgl-workspace/sglang/python/sglang/srt/speculative/dflash_utils.py \
  /sgl-workspace/sglang/python/sglang/srt/speculative/dflash_worker_v2.py \
  /sgl-workspace/sglang/python/sglang/srt/model_executor/forward_batch_info.py \
  /sgl-workspace/sglang/python/sglang/srt/mem_cache/memory_pool.py \
  /sgl-workspace/sglang/python/sglang/srt/mem_cache/swa_memory_pool.py \
  /sgl-workspace/sglang/python/sglang/srt/managers/tp_worker.py \
  > "$root/installed-source.sha256"
python3 - "$packet/SOURCE_BINDING.json" "$root/installed-source.sha256" <<'PY'
import json
import pathlib
import re
import sys

binding = json.loads(pathlib.Path(sys.argv[1]).read_text())
expected = {row["source_path"]: row["sha256"] for row in binding["executed_source"]}
observed = {}
for line in pathlib.Path(sys.argv[2]).read_text().splitlines():
    if not re.match(r"^[0-9a-f]{64}\s+", line):
        continue
    digest, path = line.split(None, 1)
    normalized = path.removeprefix("/sgl-workspace/sglang/")
    if normalized in observed:
        raise SystemExit(f"duplicate installed source record: {normalized}")
    observed[normalized] = digest
if observed != expected:
    raise SystemExit(f"installed source mismatch: observed={observed!r}")
PY

stage=server-start
sudo -n docker rm -f "$container" >/dev/null 2>&1 || true
sudo -n docker run -d --name "$container" --gpus all --ipc=host --network host \
  -e PYTHONPATH=/observer:/packet/observer \
  -e REQUEST25_BOUNDARY_CAPTURE=/work/request25-boundary.json \
  -e REQUEST25_SOURCE_BINDING_SHA256="$source_binding" \
  -v "$models:/models:ro" \
  -v "$packet:/packet:ro" \
  -v "$root:/work" \
  -v "$root/observer:/observer:ro" \
  "$image" \
  python3 -m sglang.launch_server \
    --model-path /models/target \
    --tokenizer-path /models/target \
    --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 \
    --dtype bfloat16 \
    --tp-size 1 \
    --attention-backend triton \
    --host 0.0.0.0 \
    --port 30000 \
    --context-length 5000 \
    --max-running-requests 1 \
    --mem-fraction-static 0.85 \
    --skip-server-warmup \
    --speculative-algorithm DFLASH \
    --speculative-draft-model-path /models/draft \
    --speculative-draft-model-revision eabd648301ce28583cc14757912e5e0f84e152e1 \
    --speculative-num-draft-tokens 4 \
    --speculative-draft-attention-backend fa4 \
  > "$root/container-id"
for _ in $(seq 1 100); do
  if curl -fsS http://127.0.0.1:30000/v1/models > "$root/models.json"; then
    break
  fi
  if ! sudo -n docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -qx true; then
    exit 70
  fi
  sleep 3
done
curl -fsS http://127.0.0.1:30000/v1/models > "$root/models.json"
python3 - "$root/ATTACH_PROOF.json" "$packet" "$source_binding" <<'PY'
import datetime
import hashlib
import json
import pathlib
import sys

packet = pathlib.Path(sys.argv[2])
pathlib.Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "attached_at_utc": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
            "packet_identity_sha256": packet.name,
            "source_binding_sha256": sys.argv[3],
            "observer_sha256": hashlib.sha256((packet / "observer/request25_boundary_probe_sitecustomize.py").read_bytes()).hexdigest(),
            "server_healthy": True,
        },
        sort_keys=True,
    )
    + "\n"
)
PY

stage=request25-science
science_started=true
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$packet/observer" python3 "$runner" \
  --output "$root/REQUEST25_RESPONSE.json" \
  --science-started "$root/REQUEST25_SCIENCE_STARTED.json"
stage=boundary-retrieval
test -s "$root/request25-boundary.json"
test ! -e "$root/request25-boundary.error.json"
science_started=false
stage=complete
trap - EXIT
finish
