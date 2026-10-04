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

fail() { printf '%s\n' "$1" >&2; exit 1; }
flag() { grep -Fxq -- "$1" "$TEST_ARGS"; }
value() {
    awk -v flag="$1" -v expected="$2" '$0 == flag {getline; if ($0 == expected) found=1} END {exit !found}' "$TEST_ARGS" \
        || fail "expected $1 $2"
}
launch() { rm -f "$TEST_ARGS" "$TEST_MASK"; bash "$1"; }
glm="$root/glm-5-3-flash/start.sh"
deepseek="$root/deepseek-v4-1-flash/start.sh"

if (unset GLM_MODEL_PATH; launch "$glm") 2>/dev/null; then fail 'GLM started without GLM_MODEL_PATH'; fi
[[ ! -e $TEST_ARGS ]] || fail 'GLM reached vLLM without GLM_MODEL_PATH'

GLM_MODEL_PATH=/models/glm launch "$glm"
value --host 127.0.0.1
value --port 8000
value --served-model-name zai-org/GLM-5.3-Flash
if flag --moe-backend; then fail 'GLM set a MoE backend by default'; fi

GLM_MODEL_PATH=/models/glm CUDA_VISIBLE_DEVICES=GPU-a,GPU-b RUNTIME_PORT=8002 VLLM_MOE_BACKEND=deep_gemm launch "$glm"
[[ $(cat "$TEST_MASK") == GPU-a,GPU-b ]] || fail 'GLM did not keep CUDA_VISIBLE_DEVICES'
value --tensor-parallel-size 2
value --port 8002
value --moe-backend deep_gemm
value --scheduling-policy priority
flag --enable-prompt-tokens-details || fail 'GLM did not enable prompt token details'

launch "$deepseek"
value --host 127.0.0.1
value --port 8000
value --served-model-name deepseek-ai/DeepSeek-V4.1-Flash
value --max-num-queued-reqs 64
value --max-num-queued-tokens 1048576

MAX_QUEUED_REQUESTS=8 MAX_QUEUED_TOKENS=4096 launch "$deepseek"
value --max-num-queued-reqs 8
value --max-num-queued-tokens 4096

for speculation in 0 1; do
    SPECULATIVE_DECODING=$speculation launch "$deepseek"
    value --revision dba1be0a40aa45a94ad051997016db3960a90277
    value --tensor-parallel-size 4
    flag --enable-prompt-tokens-details || fail 'DeepSeek did not enable prompt token details'

    if [[ $speculation == 1 ]]; then
        flag --speculative-config || fail 'speculation was not enabled'
        python3 - "$TEST_ARGS" <<'PYTEST'
import json
import sys
from pathlib import Path
args = Path(sys.argv[1]).read_text().splitlines()
config = json.loads(args[args.index("--speculative-config") + 1])
assert config["revision"] == args[args.index("--revision") + 1], "draft must reuse the pinned target revision"
PYTEST
    elif flag --speculative-config; then
        fail 'speculation was not disabled'
    fi
done

status=0
SPECULATIVE_DECODING=true launch "$deepseek" 2>/dev/null || status=$?
[[ $status == 64 ]] || fail "DeepSeek accepted SPECULATIVE_DECODING=true with status $status"
[[ ! -e $TEST_ARGS ]] || fail 'DeepSeek reached vLLM with an invalid SPECULATIVE_DECODING'

printf 'Model launch checks passed.\n'
