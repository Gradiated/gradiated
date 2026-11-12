#!/usr/bin/env bash
# KnowLine-31B-Gen1.5 on the dev sample (or panel), then REAX-style ensembles of it with a Gradiated Decide run and
# with the base, each scored against COMPARE. Usage on the VM:
#   run-ensemble-eval.sh [OTHER_RUN=runs/evals/gd-v1-s1652-a0.5-sample] [sample|panel]
# Env: BACKEND=knowline-http (release SGLang servers, vm/serve-knowline.sh; or knowline: transformers, ~4x slower),
#      KL_NAME (run name, default knowline-sgl / knowline), WEIGHTS="0.5" (KnowLine's weights; the other run gets 1 - w), MODES="linear" (or "linear log"),
#      COMPARE=runs/evals/base-$WHICH, BASE_RUN=runs/evals/base-$WHICH.
set -euo pipefail
source "$HOME/gdecide/env.sh"
OTHER=${1:-runs/evals/gd-v1-s1652-a0.5-sample}; WHICH=${2:-sample}
WEIGHTS=${WEIGHTS:-0.5}; MODES=${MODES:-linear}
BACKEND=${BACKEND:-knowline-http}; KL_NAME=${KL_NAME:-knowline$([ "$BACKEND" = knowline-http ] && echo -sgl)}
BASE_RUN=${BASE_RUN:-runs/evals/base-$WHICH}; COMPARE=${COMPARE:-runs/evals/base-$WHICH}
KL_REVISION=8e56aa1b236a6dd1064dcfd22ba1e5e360e4c140
cd "$ROOT"
PY=$ROOT/venv/bin/python; export PATH=$HOME/.local/bin:$PATH
"$PY" -c "import requests" 2>/dev/null || VIRTUAL_ENV=$ROOT/venv uv pip install -q requests

if [ ! -f ckpt/knowline/done ]; then
  HF_HUB_DISABLE_XET=1 "$PY" -c "
from huggingface_hub import snapshot_download
snapshot_download('PelaAI/KnowLine-31B-Gen1.5', revision='$KL_REVISION', local_dir='ckpt/knowline', max_workers=16)"
  (cd ckpt/knowline && sha256sum --quiet --ignore-missing -c SHA256SUMS) || { echo "KnowLine SHA256SUMS mismatch" >&2; exit 1; }
  echo "$KL_REVISION" > ckpt/knowline/done
fi

# Inputs that bootstrap does not restore.
for run in "$OTHER" "$BASE_RUN" "$COMPARE"; do
  [ -s "$run/results.jsonl" ] || ls "$run"/results-*.jsonl >/dev/null 2>&1 || \
    aws s3 cp --only-show-errors "$S3_PREFIX/$run/results.jsonl" "$run/results.jsonl"
done

KL=runs/evals/$KL_NAME-$WHICH
if [ ! -f "$KL/done" ]; then
  if [ "$BACKEND" = knowline-http ]; then bash src/gradiated-decide/vm/serve-knowline.sh "$ROOT/ckpt/knowline"; fi
  COMPARE=$COMPARE bash src/gradiated-decide/vm/run-eval.sh "$KL_NAME" "$ROOT/ckpt/knowline" "$WHICH" --backend "$BACKEND"
fi

ensemble() {  # NAME OTHER_RUN W MODE
  local out=runs/evals/$1-$WHICH other_w
  other_w=$(python3 -c "print(round(1 - $3, 6))")
  mkdir -p "$out"
  (cd src/gradiated-decide && "$PY" -m gdecide.ensemble --runs "$ROOT/$KL" "$ROOT/$2" --weights "$3" "$other_w" \
     --mode "$4" --out "$ROOT/$out" > "$ROOT/$out/ensemble.log" 2>&1 && \
   "$PY" -m gdecide.score --suite "$ROOT/suite/suite-0.3" --run "$ROOT/$out" --sample "$ROOT/suite/$WHICH-ids.json" \
     --compare "$ROOT/$COMPARE" > "$ROOT/$out/score.log" 2>&1)
  touch "$out/done"
  aws s3 sync --only-show-errors "$out" "$S3_PREFIX/$out" --exclude "results-*.jsonl"
  echo "{\"ensemble\": \"$1\", \"other\": \"$2\", \"knowline_weight\": $3, \"mode\": \"$4\", \"index\": $(python3 -c "import json;d=json.load(open('$out/gdecide-score.json'));print(json.dumps({'index': d['index'], 'delta_index': d.get('delta_index')}))")}" | tee -a "runs/evals/ensembles-$WHICH.jsonl"
}

other_name=$(basename "$OTHER"); other_name=${other_name%-$WHICH}
for w in $WEIGHTS; do
  for mode in $MODES; do
    suffix=w$w$([ "$mode" = linear ] || echo "-$mode")
    ensemble "ens-$KL_NAME+$other_name-$suffix" "$OTHER" "$w" "$mode"
    ensemble "ens-$KL_NAME+base-$suffix" "$BASE_RUN" "$w" "$mode"
  done
done
aws s3 cp --only-show-errors "runs/evals/ensembles-$WHICH.jsonl" "$S3_PREFIX/runs/evals/ensembles-$WHICH.jsonl"
