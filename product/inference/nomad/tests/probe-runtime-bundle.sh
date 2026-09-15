#!/usr/bin/env bash
# Run inside an existing GPU provider container. Does not start a model server.
# Usage: timeout --kill-after=15s 600s bash probe-runtime-bundle.sh VENV_PATH
set -euo pipefail
source_env=$(realpath "${1:?Pass the existing self-contained venv path}")
[[ -f "$source_env/pyvenv.cfg" ]]
grep -qi '^include-system-site-packages = false$' "$source_env/pyvenv.cfg"
work=$(mktemp -d /tmp/gradiated-runtime-bundle.XXXXXX)
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
# Leave space for the archive, extracted environment, and a 4 GiB margin.
size=$(du -sk "$source_env" | awk '{print $1}')
free=$(df -Pk "$work" | awk 'NR==2 {print $4}')
((free > size * 2 + 4194304)) || {
  echo 'Insufficient temporary disk space' >&2
  exit 1
}
export PYTHONDONTWRITEBYTECODE=1
printf 'phase=archive time=%s\n' "$(date -u +%FT%TZ)"
tar -C "$source_env" -cf "$work/runtime.tar" .
(cd "$work" && sha256sum runtime.tar >runtime.sha256 && sha256sum -c runtime.sha256)
cat "$work/runtime.sha256"
mkdir "$work/runtime"
printf 'phase=extract time=%s\n' "$(date -u +%FT%TZ)"
tar -C "$work/runtime" -xf "$work/runtime.tar"
# Use the relocated interpreter, not console scripts with absolute shebangs.
# Python here tests the Python serving runtime; it is not a GPU agent service.
printf 'phase=runtime time=%s\n' "$(date -u +%FT%TZ)"
"$work/runtime/bin/python" -I -B - "$work/runtime" <<'PY'
import json
import pathlib
import sys
import torch
import vllm
root = pathlib.Path(sys.argv[1]).resolve()
for module in (torch, vllm):
    assert pathlib.Path(module.__file__).resolve().is_relative_to(root), module.__file__
assert pathlib.Path(sys.prefix).resolve() == root
count = torch.cuda.device_count()
assert count == 4, count
for index in range(count):
    value = torch.ones(1, device=f"cuda:{index}")
    assert value.add(1).item() == 2
    del value
    torch.cuda.empty_cache()
print(json.dumps({"runtime_relocated": True, "vllm": vllm.__version__,
                  "torch": torch.__version__, "cuda": torch.version.cuda,
                  "gpu_count": count, "tiny_cuda_operation": "passed"}))
PY
CUDA_VISIBLE_DEVICES='' "$work/runtime/bin/python" -I -B -m vllm.entrypoints.cli.main --help >"$work/help.txt"
grep -q 'serve' "$work/help.txt"
printf 'phase=complete time=%s cli_help=passed\n' "$(date -u +%FT%TZ)"
