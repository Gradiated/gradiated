#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_global_head_dim256_attention_distillation
unit=gemma4-head256-attention-distill-r1-20260718t2319z
systemd-run --user --unit "$unit" --collect --property=TimeoutStartSec=80min /bin/bash "$project/run_owner.sh"
printf '%s.service\n' "$unit"
