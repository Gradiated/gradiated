#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/vllm" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$TEST_ARGS"
printf '%s' "${CUDA_VISIBLE_DEVICES:-}" > "$TEST_MASK"
MOCK
chmod +x "$work/vllm"
export VLLM_BIN="$work/vllm" TEST_ARGS="$work/args" TEST_MASK="$work/mask"
flag() { grep -Fxq -- "$1" "$TEST_ARGS"; }
value() { awk -v flag="$1" -v expected="$2" '$0 == flag {getline; if ($0 == expected) found=1} END {exit !found}' "$TEST_ARGS"; }
GLM_MODEL_PATH=/models/glm CUDA_VISIBLE_DEVICES=GPU-a,GPU-b RUNTIME_PORT=8002 VLLM_MOE_BACKEND=deep_gemm bash "$root/glm-5-3-flash/start.sh"
[[ $(cat "$TEST_MASK") == GPU-a,GPU-b ]]
value --tensor-parallel-size 2
value --port 8002
value --moe-backend deep_gemm
value --scheduling-policy priority
flag --enable-prompt-tokens-details
for speculation in 0 1; do
    SPECULATIVE_DECODING=$speculation bash "$root/deepseek-v4-1-flash/start.sh"
    value --revision dba1be0a40aa45a94ad051997016db3960a90277
    value --tensor-parallel-size 4
    flag --enable-prompt-tokens-details
    if [[ $speculation == 1 ]]; then flag --speculative-config; else ! flag --speculative-config; fi
done
printf 'Model launch checks passed.\n'
