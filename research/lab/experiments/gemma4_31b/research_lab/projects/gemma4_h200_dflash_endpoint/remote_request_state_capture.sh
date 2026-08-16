#!/usr/bin/env bash
set -Eeuo pipefail

packet=$1
root=$2
scope=${3:-both}
models=/home/glmrunner/gemma4-dflash/work/models
image=gemma4-dflash-sglang:588d1f7bc942-cycle-oracle
target_revision=b9ea41a2887d8607f594846523f94c6cc75ac8a4
draft_revision=eabd648301ce28583cc14757912e5e0f84e152e1
container=gemma4-dflash

mkdir -p "$root/results" "$root/states" "$root/observer"
install -m 0444 "$packet/request_state_capture_sitecustomize.py" "$root/observer/sitecustomize.py"
install -m 0444 "$packet/request_state_observer.py" "$root/observer/request_state_observer.py"

stage=preflight
active_arm=none
science_started=false
finish() {
  rc=$?
  sudo -n docker logs "$container" > "$root/${active_arm}.server.latest.log" 2>&1 || true
  sudo -n docker inspect "$container" > "$root/${active_arm}.container.latest.json" 2>&1 || true
  python3 - "$root/REMOTE_TERMINAL.json" "$stage" "$active_arm" "$rc" "$science_started" <<'PY'
import json
import pathlib
import sys

pathlib.Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "stage": sys.argv[2],
            "active_arm": sys.argv[3],
            "exit_code": int(sys.argv[4]),
            "science_started": sys.argv[5] == "true",
        },
        sort_keys=True,
    )
    + "\n"
)
PY
}
trap finish EXIT

(cd "$packet" && sha256sum -c PACKET.sha256)
sudo -n docker run --rm "$image" sha256sum \
  /sgl-workspace/sglang/python/sglang/srt/speculative/dflash_worker_v2.py \
  /sgl-workspace/sglang/python/sglang/srt/speculative/dflash_info_v2.py \
  /sgl-workspace/sglang/python/sglang/srt/managers/tp_worker.py \
  /sgl-workspace/sglang/python/sglang/srt/model_executor/forward_batch_info.py \
  /sgl-workspace/sglang/python/sglang/srt/mem_cache/memory_pool.py \
  /sgl-workspace/sglang/python/sglang/srt/mem_cache/swa_memory_pool.py \
  | sed -n -E '/^[0-9a-f]{64}  \/sgl-workspace\/sglang\/python\/sglang\/srt\//p' \
  > "$root/installed-source.sha256"
test "$(wc -l < "$root/installed-source.sha256")" -eq 6
diff -u "$packet/EXPECTED_INSTALLED_SOURCE.sha256" "$root/installed-source.sha256"

stop_server() {
  sudo -n docker rm -f "$container" >/dev/null 2>&1 || true
}

start_server() {
  active_arm=$1
  shift
  stop_server
  sudo -n docker run -d --name "$container" --gpus all --ipc=host --network host \
    -e PYTHONPATH=/observer \
    -e REQUEST_STATE_ARM="$active_arm" \
    -e REQUEST_STATE_CAPTURE="/work/states/$active_arm.jsonl" \
    -v "$models:/models:ro" \
    -v "$packet:/packet:ro" \
    -v "$root:/work" \
    -v "$root/observer:/observer:ro" \
    "$image" \
    python3 -m sglang.launch_server \
      --model-path /models/target \
      --tokenizer-path /models/target \
      --revision "$target_revision" \
      --dtype bfloat16 \
      --tp-size 1 \
      --attention-backend triton \
      --host 0.0.0.0 \
      --port 30000 \
      --context-length 5000 \
      --max-running-requests 32 \
      --mem-fraction-static 0.85 \
      --skip-server-warmup \
      "$@" > "$root/$active_arm.container-id"
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models > "$root/$active_arm.models.json"; then
      return 0
    fi
    sleep 3
  done
  sudo -n docker logs "$container" > "$root/$active_arm.server.log" 2>&1 || true
  return 1
}

run_arm() {
  active_arm=$1
  if test -s "$root/results/$active_arm/TERMINAL.json" \
    && test -s "$root/states/$active_arm.jsonl" \
    && test ! -e "$root/states/$active_arm.observer-error"; then
    return 0
  fi
  rm -rf "$root/results/$active_arm"
  rm -f "$root/states/$active_arm.jsonl" "$root/states/$active_arm.observer-error"
  stage="$active_arm-server"
  if test "$active_arm" = ar-c32; then
    start_server "$active_arm"
  else
    start_server "$active_arm" \
      --speculative-algorithm DFLASH \
      --speculative-draft-model-path /models/draft \
      --speculative-draft-model-revision "$draft_revision" \
      --speculative-num-draft-tokens 4 \
      --speculative-draft-attention-backend fa4
  fi
  stage="$active_arm-science"
  science_started=true
  python3 - "$root/$active_arm.SCIENCE_STARTED.json" "$active_arm" <<'PY'
import datetime
import json
import pathlib
import sys

pathlib.Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "arm": sys.argv[2],
            "started_at_utc": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        },
        sort_keys=True,
    )
    + "\n"
)
PY
  sudo -n docker exec "$container" python3 /packet/dflash_endpoint_runner.py \
    --arm "$active_arm" \
    --concurrency 32 \
    --output "/work/results/$active_arm"
  stage="$active_arm-retrieval-boundary"
  sudo -n docker logs "$container" > "$root/$active_arm.server.log" 2>&1
  sudo -n docker inspect "$container" > "$root/$active_arm.container.json" 2>&1
  test -s "$root/results/$active_arm/TERMINAL.json"
  test -s "$root/states/$active_arm.jsonl"
  test ! -e "$root/states/$active_arm.observer-error"
  stop_server
  science_started=false
}

case "$scope" in
  both)
    run_arm ar-c32
    run_arm dflash-depth4-c32
    ;;
  ar)
    run_arm ar-c32
    ;;
  dflash)
    run_arm dflash-depth4-c32
    ;;
  *)
    echo "unknown scope: $scope" >&2
    exit 2
    ;;
esac

stage=complete
active_arm=none
science_started=false
stop_server
trap - EXIT
python3 - "$root/REMOTE_TERMINAL.json" <<'PY'
import json
import pathlib
import sys

pathlib.Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "stage": "complete",
            "active_arm": "none",
            "exit_code": 0,
            "science_started": False,
        },
        sort_keys=True,
    )
    + "\n"
)
PY
