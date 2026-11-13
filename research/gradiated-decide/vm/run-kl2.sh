#!/usr/bin/env bash
# gd-kl2: continue gd-kl1 (its final export, KnowLine family) on mixes/kl2-targeted.json, the sources aimed at
# gd-kl1's measured misses (JevBench temporal_numeric / long_policy / judge_hard; Decision Index benchmarks where the
# pplx family beats it), then blend with KnowLine at 1.0 / 0.7 / 0.5, score the blends on the dev sample, the best on
# the full panel, and the 0.5 blend on Google's Gemini Decision 1 panel. Same loss and schedule as gd-kl1, lower LR.
# Usage on the VM: run-kl2.sh [STEPS=1000]   (idempotent; data, states, exports and results in S3)
set -euo pipefail
source "$HOME/gdecide/env.sh"
STEPS=${1:-1000}
cd "$ROOT"
V=src/gradiated-decide/vm
PY=$ROOT/venv/bin/python
mkdir -p logs
bash $V/get-knowline.sh
# data/extra was never decontaminated; the kl2 mix reads data/extra-clean (gdecide.decontam against the suite, its pools
# and the JevBench public + Gemini panel items in suite/extra-items.jsonl).
if [ ! -f data/extra-clean/done ]; then
  if aws s3 ls "$S3_PREFIX/data/extra-clean/done" >/dev/null 2>&1; then
    aws s3 sync --only-show-errors "$S3_PREFIX/data/extra-clean" data/extra-clean
  else
    aws s3 sync --only-show-errors "$S3_PREFIX/data/extra" data/extra
    aws s3 sync --only-show-errors "$S3_PREFIX/suite" suite
    (cd src/gradiated-decide && $PY -m gdecide.decontam --suite "$ROOT/suite/suite-0.3" --pools "$ROOT"/suite/pools/*.jsonl.gz \
      --inputs "$ROOT/data/extra/*.jsonl.gz" --out "$ROOT/data/extra-clean" --extra-items "$ROOT/suite/extra-items.jsonl" --workers 32) \
      > logs/decontam-extra.log 2>&1
    touch data/extra-clean/done
    aws s3 sync --only-show-errors data/extra-clean "$S3_PREFIX/data/extra-clean"
  fi
fi
if [ ! -f data/kl2/done ]; then
  if aws s3 ls "$S3_PREFIX/data/kl2/done" >/dev/null 2>&1; then
    aws s3 sync --only-show-errors "$S3_PREFIX/data/kl2" data/kl2
  else
    (cd src/gradiated-decide && $PY -m gdecide.prepare --family gemma --checkpoint "$ROOT/ckpt/knowline" --mix mixes/kl2-targeted.json \
      --out "$ROOT/data/kl2" --workers 48)
    touch data/kl2/done
    aws s3 sync --only-show-errors data/kl2 "$S3_PREFIX/data/kl2"
  fi
fi
[ -f runs/gd-kl1/export-1155/done ] || aws s3 sync --only-show-errors "$S3_PREFIX/runs/gd-kl1/export-1155" runs/gd-kl1/export-1155
# Throughput bench first (vm/bench-train.sh), then train with the fastest configuration that ran and kept peak memory
# under 85% of the GPU; if that run fails, resume from its state with the default settings.
[ -f logs/bench-gemma.args ] || {
  bash $V/bench-train.sh gemma kl2 "$ROOT/runs/gd-kl1/export-1155" > logs/bench-gemma.log 2>&1 || true
  $PY - logs/bench-gemma.tsv "$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)" > logs/bench-gemma.args <<'EOF2'
import csv, sys
rows = [r for r in csv.DictReader(open(sys.argv[1]), delimiter="\t") if r["status"] == "ok" and float(r["mem_gib"]) < 0.85 * float(sys.argv[2]) / 1024]
flags = {"base": "", "noreshard": "--no-reshard", "compile": "--compile", "flex": "--attn flex_attention"}
best = max(rows, key=lambda r: float(r["tokens_per_s"]), default={"config": "base"})
name = best["config"]
if name == "combo":
    print(open("logs/bench-gemma-combo.args").read().strip())
else:
    print(flags.get(name, f"--keep-activations {name[4:]}" if name.startswith("keep") else ""))
EOF2
}
TRAIN=(--family gemma --epochs 1 --max-steps "$STEPS" --lr 2e-6 --readout-lr 1e-5 --brier 0.5 --warmup 30 --state-minutes 30 --dev-every 250 --seed 20261113)
if ! grep -q '"event": "finished"' runs/gd-kl2/train.log.jsonl 2>/dev/null; then
  read -ra FAST < logs/bench-gemma.args || FAST=()
  CKPT=$ROOT/runs/gd-kl1/export-1155 bash $V/run-train.sh gd-kl2 kl2 "${TRAIN[@]}" "${FAST[@]}" > logs/train-gd-kl2.log 2>&1 || \
    CKPT=$ROOT/runs/gd-kl1/export-1155 bash $V/run-train.sh gd-kl2 kl2 "${TRAIN[@]}" > logs/train-gd-kl2-fallback.log 2>&1
fi
[ -f runs/gd-kl2/after-train-done ] || FAMILY=gemma bash $V/after-train.sh gd-kl2 "1.0 0.7 0.5" > logs/after-gd-kl2.log 2>&1
STEP=$(ls -d runs/gd-kl2/export-*/ | sort -t- -k3 -n | tail -1 | sed 's#.*export-\([0-9]*\)/#\1#')
[ -f "runs/external/gd-kl2-s$STEP-a0.5/done" ] || bash $V/run-knowline-external.sh gd-kl2 "$STEP" 0.5 > logs/kl2-external.log 2>&1
touch logs/kl2-finished
