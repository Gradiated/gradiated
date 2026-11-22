#!/bin/bash -p
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "$project_dir/../../../../.." && pwd)"
exec "$repo_root/.agents/runtime/hardware/inference/venv/bin/python" -I -B -S "$project_dir/tools/generative.py" "$@"
