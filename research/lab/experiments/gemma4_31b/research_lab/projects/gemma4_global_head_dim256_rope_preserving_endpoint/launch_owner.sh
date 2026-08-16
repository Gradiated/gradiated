#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_global_head_dim256_rope_preserving_endpoint
unit=gemma4-global-head256-rope-c32-20260718t2240z
systemd-run --user --unit "$unit" --collect --property=TimeoutStartSec=45min /bin/bash "$project/run_owner.sh"
printf '%s.service\n' "$unit"
