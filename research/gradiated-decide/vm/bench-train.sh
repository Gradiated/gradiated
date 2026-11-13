#!/usr/bin/env bash
# Throughput bench for gdecide.train_full: short --bench runs (no dev, state or export) of the speed options. Reports
# steady-state tokens/s (the mean of the logged windows after step 10), peak memory, the step-1 loss (the same batch
# before any update, so it should match the baseline up to kernel rounding unless --balance changes the batch) and each
# config's flags, which run-kl2.sh reads to train with the fastest.
# Usage on the VM: bench-train.sh FAMILY DATA CKPT [STEPS=30]   (FAMILY qwen|gemma; results in logs/bench-FAMILY.tsv)
set -uo pipefail
source "$HOME/gdecide/env.sh"
FAMILY=$1; DATA=$2; CKPT=$3; STEPS=${4:-30}
cd "$ROOT"
mkdir -p logs runs/bench
[ -f "data/$DATA/done" ] || { aws s3 sync --only-show-errors "$S3_PREFIX/data/$DATA" "data/$DATA"; touch "data/$DATA/done"; }
TSV=logs/bench-$FAMILY.tsv
[ -f "$TSV" ] || printf 'config\tstatus\ttokens_per_s\tmem_gib\tce_step1\targs\n' > "$TSV"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True NCCL_NVLS_ENABLE=0

bench() {  # bench NAME [train_full args...]
  local name=$1; shift
  grep -q "^$name	" "$TSV" && return
  local out=runs/bench/$FAMILY-$name; rm -rf "$out"
  (cd src/gradiated-decide && timeout 3600 ../../venv/bin/python -m torch.distributed.run --standalone --nproc-per-node 8 -m gdecide.train_full \
    --checkpoint "$CKPT" --data "$ROOT/data/$DATA" --out "$ROOT/$out" --family "$FAMILY" --max-steps "$STEPS" --warmup 5 --lr 1e-6 \
    --bench "$@") > "logs/bench-$FAMILY-$name.log" 2>&1
  local code=$?
  "$ROOT/venv/bin/python" - "$name" "$code" "$out/train.log.jsonl" "$*" >> "$TSV" <<'EOF'
import json, sys
name, code, path, args = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4].replace("--profile", "").strip()
try:
    rows = [json.loads(l) for l in open(path) if '"train"' in l]
except OSError:
    rows = []
rows = [r for r in rows if r.get("event") == "train"]
steady = [r["recent_tokens_per_s"] for r in rows if r["step"] > 10]
ce = next((r["ce"] for r in rows if r["step"] == 1), "")
status = "ok" if code == 0 and steady else f"fail({code})"
tps = round(sum(steady) / len(steady)) if steady else 0
mem = max((r["mem_gib"] for r in rows), default=0)
print(f"{name}\t{status}\t{tps}\t{mem}\t{ce}\t{args}")
EOF
  tail -n 1 "$TSV"
}

bench base
bench keep8 --keep-activations 8
bench balance --balance
if [ "$FAMILY" = gemma ]; then
  bench fast --attn gd_fast
  bench balance-fast --balance --attn gd_fast --profile
  bench balance-fast-keep8 --balance --attn gd_fast --keep-activations 8
  bench balance-fast-keep16 --balance --attn gd_fast --keep-activations 16
  bench balance-fast-noreshard --balance --attn gd_fast --no-reshard
else
  bench balance-keep8 --balance --keep-activations 8
  bench balance-noreshard --balance --no-reshard
fi
cp "$TSV" "runs/bench/" ; aws s3 sync --only-show-errors runs/bench "$S3_PREFIX/runs/bench" --exclude '*/state-*'
aws s3 sync --only-show-errors logs "$S3_PREFIX/logs"
