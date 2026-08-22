#!/usr/bin/env bash
set -euo pipefail

bundle_root=${1:?bundle root required}
venv_root=${2:?venv root required}
"${PYTHON_BIN:-python3}" -m venv "$venv_root"
"$venv_root/bin/python" -m pip install --no-index --find-links "$bundle_root/wheels" --requirement "$bundle_root/requirements.runtime.lock"
"$venv_root/bin/python" -m pip check
