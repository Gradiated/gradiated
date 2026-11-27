#!/usr/bin/env bash
# Start KnowLine's release server (serve_knowline.sh: SGLang + knowline_server.py) on every GPU, front ends on
# BASE_PORT + gpu, and wait until all answer. Usage on the VM: serve-knowline.sh MODEL_DIR [BASE_PORT=8080]
# MODEL_DIR must hold the release files (serve_knowline.sh, knowline_server.py, knowline_layout.py, temperatures.json).
# SGLang lives in its own environment ($ROOT/venv-sgl), pinned to the versions of KnowLine's INFERENCE.md.
# Servers of another checkpoint are stopped first; STOP=1 serve-knowline.sh MODEL only stops them.
set -euo pipefail
source "$HOME/gdecide/env.sh"
MODEL=$1; BASE_PORT=${2:-8080}
cd "$ROOT"
export PATH=$HOME/.local/bin:$PATH
if ! venv-sgl/bin/python -c "import sglang" 2>/dev/null; then
  uv venv -q -p 3.12 venv-sgl
  VIRTUAL_ENV=$ROOT/venv-sgl uv pip install -q "sglang[all]==0.5.21" "transformers==5.12.1" requests
fi
[ -f "$MODEL/serve_knowline.sh" ] || { echo "$MODEL lacks the release files" >&2; exit 1; }
mkdir -p logs/knowline-serve
GPUS=$(nvidia-smi -L | wc -l)
# Serving another checkpoint: stop those servers first (STOP=1 only stops).
if [ "${STOP:-0}" = 1 ] || { [ -f logs/knowline-serve/model ] && [ "$(cat logs/knowline-serve/model)" != "$MODEL" ]; }; then
  pkill -f '[s]erve_knowline.sh' || true; pkill -f '[k]nowline_server.py' || true; pkill -f '[s]glang.launch_server' || true
  for _ in $(seq 1 60); do pgrep -f '[s]glang' >/dev/null || break; sleep 5; done
  pkill -9 -f '[s]glang' || true; sleep 10
  rm -f logs/knowline-serve/model
  [ "${STOP:-0}" = 1 ] && exit 0
fi
echo "$MODEL" > logs/knowline-serve/model
for g in $(seq 0 $((GPUS - 1))); do
  port=$((BASE_PORT + g))
  curl -sf -m 3 "http://127.0.0.1:$port/v1/models" >/dev/null && continue
  (PATH=$ROOT/venv-sgl/bin:$PATH setsid nohup bash "$MODEL/serve_knowline.sh" "$MODEL" "$g" "$port" \
    > "logs/knowline-serve/gpu$g.log" 2>&1 < /dev/null &)
done
for g in $(seq 0 $((GPUS - 1))); do
  for _ in $(seq 1 180); do
    curl -sf -m 3 "http://127.0.0.1:$((BASE_PORT + g))/v1/models" >/dev/null && break
    sleep 10
  done
  curl -sf -m 3 "http://127.0.0.1:$((BASE_PORT + g))/v1/models" >/dev/null || { echo "GPU $g server did not start; see logs/knowline-serve/gpu$g.log" >&2; exit 1; }
done
echo "KnowLine servers up on ports $BASE_PORT-$((BASE_PORT + GPUS - 1))"
