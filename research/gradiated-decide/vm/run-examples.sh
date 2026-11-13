#!/usr/bin/env bash
# Run the decide-1 post's examples (docs/decide-1/examples.json) on decide-1 and on KnowLine-31B-Gen1.5, one GPU is
# enough. decide-1 is the gd-kl2 0.5 blend from S3; KnowLine comes from the Hub at the pinned revision.
# Usage on the VM (bundle unpacked in $ROOT/src, env.sh written): run-examples.sh   -> runs/examples/answers.jsonl
set -euo pipefail
source "$HOME/gdecide/env.sh"
cd "$ROOT"
mkdir -p logs runs/examples ckpt
export PATH=$HOME/.local/bin:$PATH
# Triton compiles a CUDA helper at SGLang start and needs the Python headers (bootstrap.sh installs them too).
dpkg -s python3.12-dev >/dev/null 2>&1 || { sudo apt-get update -qq && sudo apt-get install -y -qq python3.12-dev >/dev/null; }
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
if [ ! -x venv/bin/python ]; then uv venv -q -p 3.12 venv && VIRTUAL_ENV=$ROOT/venv uv pip install -q huggingface-hub==1.31.0 requests; fi
DECIDE=$ROOT/runs/merges/gd-kl2-s1000-a0.5
aws s3 sync --only-show-errors "$S3_PREFIX/runs/merges/gd-kl2-s1000-a0.5" "$DECIDE"
bash src/gradiated-decide/vm/get-knowline.sh
EX=src/gradiated-decide/docs/decide-1
OUT=runs/examples/answers.jsonl; : > "$OUT"
for pair in "decide-1:$DECIDE" "knowline-31b-gen1.5:$ROOT/ckpt/knowline"; do
  name=${pair%%:*}; model=${pair#*:}
  bash src/gradiated-decide/vm/serve-knowline.sh "$model"
  venv/bin/python "$EX/run_examples.py" "$EX/examples.json" http://127.0.0.1:8080 "$name" "$OUT"
done
aws s3 cp --only-show-errors "$OUT" "$S3_PREFIX/runs/examples/answers.jsonl"
echo examples-done
