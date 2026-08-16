#!/usr/bin/env bash
set -Eeuo pipefail

root=${STATIC_FP8_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"
rm -rf "$artifacts/run"
rm -f "$artifacts/REMOTE_TERMINAL.json"

terminal() {
  python3 - "$artifacts/REMOTE_TERMINAL.json" "$1" "$2" <<'PY'
import datetime, json, os, pathlib, sys
path = pathlib.Path(sys.argv[1])
state_path = path.parent / "run/INVOCATION_STATE.json"
state = json.loads(state_path.read_text()) if state_path.is_file() else {}
value = {
    "schema_version": 1,
    "status": "terminal",
    "classification": sys.argv[2],
    "message": sys.argv[3],
    "candidate_cuda_invocation_started": state.get("candidate_cuda_invocation_started", False),
    "scientific_invocation_started": state.get("scientific_invocation_started", False),
    "completed_rows": state.get("completed_rows", []),
    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
temporary = path.with_suffix(".part")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(temporary, path)
PY
}

compact() {
  set +e
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/static-fp8-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/static-fp8-compact.tar.gz" >"$root/static-fp8-compact.tar.gz.sha256"
}
trap compact EXIT
trap 'test -f "$artifacts/REMOTE_TERMINAL.json" || terminal integration_failure "$BASH_COMMAND"' ERR

sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>/dev/null || {
  sudo docker pull "$image" >"$artifacts/image-pull.stdout" 2>"$artifacts/image-pull.stderr"
  sudo docker image inspect "$image" >"$artifacts/image-inspect.json"
}

set +e
sudo docker run --rm --gpus all --ipc=host \
  -v "$root:/work" -w /work/input \
  -e PYTHONPATH=/sgl-workspace/sglang/python \
  "$image" python3 /work/input/static_fp8_consumer.py \
    --bf16 /work/input/layer0_down_proj_bf16.safetensors \
    --representation /work/input/layer0_down_proj_static_fp8.safetensors \
    --output /work/artifacts/run \
  >"$artifacts/consumer.stdout" 2>"$artifacts/consumer.stderr"
consumer_rc=$?
set -e

if [[ -f "$artifacts/run/TERMINAL.json" && ( "$consumer_rc" -eq 0 || "$consumer_rc" -eq 20 ) ]]; then
  terminal component_complete "consumer_rc=$consumer_rc"
else
  terminal integration_failure "consumer_rc=$consumer_rc"
fi

