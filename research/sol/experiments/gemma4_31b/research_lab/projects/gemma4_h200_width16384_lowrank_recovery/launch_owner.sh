#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_width16384_lowrank_recovery
unit=gemma4-width16384-lowrank-recovery-20260723t1802
exec systemd-run --user --unit "$unit" --collect \
  --property=TimeoutStartSec=6h \
  /usr/bin/python3 "$project/run_bench_owner.py" \
  --unit "$unit.service" --unit-manager user
