#!/usr/bin/env bash
# Probe: fine-tune gd-v1 (0.5 blend) briefly on code-labelled date/number reasoning (gdecide.data.reasoning_gen) plus
# replay, then compare it with gd-v1 on the generator's held-out test split and on Google's panel (incl. JevBench).
# Usage on the VM: run-probe.sh   (idempotent; results under runs/external/ and in S3)
set -euo pipefail
source "$HOME/gdecide/env.sh"
cd "$ROOT"
V=src/gradiated-decide/vm
PY=$ROOT/venv/bin/python
GDV1=$ROOT/runs/merges/gd-v1-s1652-a0.5
[ -f "$GDV1/done" ] || { echo "missing $GDV1 (run run-external.sh with merge:gd-v1/export-1652:0.5 first)" >&2; exit 1; }
cd src/gradiated-decide
[ -f "$ROOT/data/reasoning/reasoning-gen.jsonl.gz" ] || \
  $PY -m gdecide.data.reasoning_gen --out "$ROOT/data/reasoning" --n 60000 --seed 1 --test-n 3000 --test-seed 999
[ -s "$ROOT/external/reasoning-test-items.jsonl" ] || \
  $PY -m gdecide.external items-from-rows --rows "$ROOT/data/reasoning/reasoning-gen-test.jsonl.gz" --out "$ROOT/external/reasoning-test-items.jsonl"
if [ ! -f "$ROOT/data/probe-reasoning/done" ]; then
  $PY -m gdecide.prepare --checkpoint "$ROOT/ckpt/base" --mix mixes/probe-reasoning.json --out "$ROOT/data/probe-reasoning" --workers 48
  touch "$ROOT/data/probe-reasoning/done"
  aws s3 sync --only-show-errors "$ROOT/data/probe-reasoning" "$S3_PREFIX/data/probe-reasoning"
fi
cd "$ROOT"
grep -q '"event": "finished"' runs/probe-reasoning/train.log.jsonl 2>/dev/null || \
  CKPT=$GDV1 VENV=venv-cc bash $V/run-train.sh probe-reasoning probe-reasoning --epochs 1 --lr 3e-6 --readout-lr 1e-5 \
    --brier 0.5 --warmup 20 --state-minutes 30 --dev-every 0 > logs/train-probe-reasoning.log 2>&1
FINAL=$(ls -d runs/probe-reasoning/export-*/ | sort -t- -k3 -n | tail -1); FINAL=${FINAL%/}
for pair in "gd-v1-s1652-a0.5:$GDV1" "probe-reasoning:$ROOT/$FINAL"; do
  name=${pair%%:*}; ckpt=${pair#*:}
  ITEMS=external/reasoning-test-items.jsonl bash $V/run-external.sh "gen-$name" "$ckpt"
done
bash $V/run-external.sh probe-reasoning "$ROOT/$FINAL"
