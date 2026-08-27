#!/usr/bin/env bash
set -euo pipefail

script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "${PYTHON_BIN:-python3}" "${script_directory}/report_status.py"
