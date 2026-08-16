#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-h200-mlp-w4-hybrid
input="$root/input"
current=/home/glmrunner/gemma4-h200-dense-fp8-streamk/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
artifacts="$1"
archive="$2"
mkdir -p "$artifacts" "$root/torch-extensions" "$root/counter-cache"

atomic_terminal() {
  python3 - "$artifacts/COUNTER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
value={
    'schema_version':1,
    'status':'terminal',
    'classification':sys.argv[2],
    'message':sys.argv[3],
    'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),
}
q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
os.replace(q,p)
PY
}

compact() {
  set +e
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$archive" -C "$artifacts" .
  sha256sum "$archive" >"$archive.sha256"
}

fail() {
  atomic_terminal counter_integration_failure "$1"
  exit 1
}

trap compact EXIT
trap 'test -f "$artifacts/COUNTER_TERMINAL.json" || atomic_terminal counter_integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/COUNTER_TERMINAL.json"
test -s "$current/model.safetensors.index.json" || fail current_checkpoint_missing
test -s "$input/layer0_mlp_awq.safetensors" || fail component_snapshot_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_missing

sudo docker run --rm --gpus all "$image" ncu --version \
  >"$artifacts/ncu.version.stdout" 2>"$artifacts/ncu.version.stderr" \
  || fail ncu_unavailable_in_pinned_image
sudo docker run --rm --gpus all "$image" ncu --list-sets \
  >"$artifacts/ncu.sets.stdout" 2>"$artifacts/ncu.sets.stderr" \
  || fail ncu_set_query_failed
grep -Eq '(^|[[:space:]])basic([[:space:]]|$)' "$artifacts/ncu.sets.stdout" \
  || fail ncu_basic_set_unavailable

for arm in control candidate; do
  rm -rf "$artifacts/counter-$arm"
  sudo docker run --rm --gpus all --ipc=host --cap-add SYS_ADMIN \
    -v "$root:/work" -v "$current:/current:ro" \
    -v "$root/counter-cache:/root/.cache" \
    -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
    -e TORCH_EXTENSIONS_DIR=/work/torch-extensions "$image" \
    ncu --profile-from-start off --target-processes all --set basic \
    --csv --page raw --log-file "/work/$(realpath --relative-to="$root" "$artifacts")/ncu-$arm.csv" \
    python3 /work/input/hybrid_component.py \
    --output "/work/$(realpath --relative-to="$root" "$artifacts")/counter-$arm" \
    --current-checkpoint /current \
    --w4-component /work/input/layer0_mlp_awq.safetensors \
    --counter-probe "$arm" \
    >"$artifacts/ncu-$arm.stdout" 2>"$artifacts/ncu-$arm.stderr" \
    || fail "ncu_${arm}_failed"
  python3 - "$artifacts/counter-$arm/TERMINAL.json" \
    "$artifacts/counter-$arm/INVOCATION_STATE.json" "$arm" <<'PY' \
    || fail "ncu_${arm}_terminal_invalid"
import json,sys
terminal=json.load(open(sys.argv[1]))
state=json.load(open(sys.argv[2]))
arm=sys.argv[3]
assert terminal.get('classification') == 'counter_probe_complete'
assert terminal.get('arm') == arm
assert terminal.get('finite') is True and terminal.get('nontrivial') is True
assert state.get(f'{arm}_cuda_started') is True
assert state.get(f'{arm}_science_started') is True
PY
  test -s "$artifacts/ncu-$arm.csv" || fail "ncu_${arm}_csv_missing"
done

atomic_terminal counter_complete exact_c32_control_and_candidate_basic_ncu_sets_persisted
