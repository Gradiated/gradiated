#!/usr/bin/env bash
set -euo pipefail

SGLANG_REVISION="8bb106cee94c1ccb5625cdb78ef0ee3e0cad3918"
MODEL="mlx-community/Qwen3-0.6B-4bit"
MODEL_REVISION="73e3e38d981303bc594367cd910ea6eb48349da8"

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${SGLANG_LOCAL_RUNTIME_DIR:-${product_dir}/../.cache/sglang-local}"
source_dir="${runtime_dir}/source"
venv_dir="${runtime_dir}/venv"
installed_revision_file="${venv_dir}/.installed-sglang-revision"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "The local SGLang profile currently supports Apple Silicon only." >&2
  exit 1
fi

if ! xcrun --find metal >/dev/null 2>&1; then
  echo "The Xcode Metal toolchain is required. Run: xcode-select --install" >&2
  exit 1
fi

if [[ ! -d "${source_dir}/.git" ]]; then
  mkdir -p "${runtime_dir}"
  git init "${source_dir}"
  git -C "${source_dir}" remote add origin https://github.com/sgl-project/sglang.git
fi

if ! git -C "${source_dir}" cat-file -e "${SGLANG_REVISION}^{commit}" 2>/dev/null; then
  git -C "${source_dir}" fetch --depth 1 origin "${SGLANG_REVISION}"
fi
git -C "${source_dir}" checkout --detach --force "${SGLANG_REVISION}"

if [[ ! -f "${installed_revision_file}" ]] || \
  [[ "$(<"${installed_revision_file}")" != "${SGLANG_REVISION}" ]]; then
  uv venv --clear --python 3.12 "${venv_dir}"
  # pyproject_other.toml carries SGLang's MPS/MLX dependency set; the default pyproject.toml does not.
  cp "${source_dir}/python/pyproject_other.toml" "${source_dir}/python/pyproject.toml"
  uv pip install --python "${venv_dir}/bin/python" --editable "${source_dir}/python[all_mps]"
  printf '%s\n' "${SGLANG_REVISION}" >"${installed_revision_file}"
fi

export SGLANG_USE_MLX=1
exec "${venv_dir}/bin/python" -m sglang.launch_server \
  --model-path "${MODEL}" \
  --revision "${MODEL_REVISION}" \
  --reasoning-parser qwen3 \
  --disable-cuda-graph \
  --max-running-requests 4 \
  --max-queued-requests 4 \
  --host 127.0.0.1 \
  --port 30000
