#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_late30_width16384_recovery
unit=gemma4-late30-width16384-recovery-20260723t1839
exec systemd-run --user --unit "$unit" --collect \
  --property=TimeoutStartSec=4h \
  /usr/bin/python3 "$project/run_bench_owner.py" \
  --unit "$unit.service" --unit-manager user
