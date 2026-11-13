#!/usr/bin/env bash
# Throughput bench for gdecide.train_full: short --bench runs (no dev, state or export) of each speed option alone, then
# every option that helped by more than 3% together. Reports steady-state tokens/s (the mean of the logged windows after
# step 10), peak memory and the step-20 loss, which should match the baseline for the maths-neutral options.
# Usage on the VM: bench-train.sh FAMILY DATA CKPT [STEPS=30]   (FAMILY qwen|gemma; results in logs/bench-FAMILY.tsv)
set -uo pipefail
source "$HOME/gdecide/env.sh"
FAMILY=$1; DATA=$2; CKPT=$3; STEPS=${4:-30}
cd "$ROOT"
mkdir -p logs runs/bench
[ -f "data/$DATA/done" ] || { aws s3 sync --only-show-errors "$S3_PREFIX/data/$DATA" "data/$DATA"; touch "data/$DATA/done"; }
TSV=logs/bench-$FAMILY.tsv
[ -f "$TSV" ] || printf 'config\tstatus\ttokens_per_s\tmem_gib\tce_step20\n' > "$TSV"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True NCCL_NVLS_ENABLE=0

bench() {  # bench NAME [train_full args...]
  local name=$1; shift
  grep -q "^$name	" "$TSV" && return
  local out=runs/bench/$FAMILY-$name; rm -rf "$out"
  (cd src/gradiated-decide && timeout 3600 ../../venv/bin/python -m torch.distributed.run --standalone --nproc-per-node 8 -m gdecide.train_full \
    --checkpoint "$CKPT" --data "$ROOT/data/$DATA" --out "$ROOT/$out" --family "$FAMILY" --max-steps "$STEPS" --warmup 5 --lr 1e-6 \
    --bench "$@") > "logs/bench-$FAMILY-$name.log" 2>&1
  local code=$?
  "$ROOT/venv/bin/python" - "$name" "$code" "$out/train.log.jsonl" >> "$TSV" <<'EOF'
import json, sys
name, code, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    rows = [json.loads(l) for l in open(path) if '"train"' in l]
except OSError:
    rows = []
rows = [r for r in rows if r.get("event") == "train"]
steady = [r["recent_tokens_per_s"] for r in rows if r["step"] > 10]
ce = next((r["ce"] for r in rows if r["step"] == 20), "")
status = "ok" if code == 0 and steady else f"fail({code})"
tps = round(sum(steady) / len(steady)) if steady else 0
mem = max((r["mem_gib"] for r in rows), default=0)
print(f"{name}\t{status}\t{tps}\t{mem}\t{ce}")
EOF
  tail -n 1 "$TSV"
}

bench base --profile
for k in 8 16 32; do bench "keep$k" --keep-activations "$k"; done
bench noreshard --no-reshard
bench compile --compile
[ "$FAMILY" = gemma ] && bench flex --attn flex_attention
# Combine the winners: the keep-activations count with the best rate, plus each boolean option that helped.
COMBO=$("$ROOT/venv/bin/python" - "$TSV" <<'EOF'
import csv, sys
rows = {r["config"]: r for r in csv.DictReader(open(sys.argv[1]), delimiter="\t")}
base = float(rows["base"]["tokens_per_s"] or 0)
good = {k: float(r["tokens_per_s"]) for k, r in rows.items() if r["status"] == "ok" and base and float(r["tokens_per_s"]) > 1.03 * base}
args = []
keep = max((k for k in good if k.startswith("keep")), key=good.get, default=None)
if keep:
    args += ["--keep-activations", keep[4:]]
for k, extra in {"noreshard": ["--no-reshard"], "compile": ["--compile"], "flex": ["--attn", "flex_attention"]}.items():
    if k in good:
        args += extra
print(" ".join(args))
EOF
)
echo "$COMBO" > "logs/bench-$FAMILY-combo.args"
[ -n "$COMBO" ] && bench combo $COMBO
cp "$TSV" "runs/bench/" ; aws s3 sync --only-show-errors runs/bench "$S3_PREFIX/runs/bench" --exclude '*/state-*'
aws s3 sync --only-show-errors logs "$S3_PREFIX/logs"
