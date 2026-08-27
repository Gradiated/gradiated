#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "$script_dir/.." && pwd)"
output_path="${1:-$root_dir/results/kv260/board_measurement.json}"
mkdir -p "$(dirname "$output_path")"

cc -std=c11 -O2 -Wall -Wextra -Werror \
  "$root_dir/host/kda_kv260_test.c" \
  -o /tmp/kda_kv260_test

if [[ "$(id -u)" -eq 0 ]]; then
  /tmp/kda_kv260_test --tokens 8 --seed 0x4b444131 | tee "$output_path"
else
  sudo /tmp/kda_kv260_test --tokens 8 --seed 0x4b444131 | tee "$output_path"
fi
