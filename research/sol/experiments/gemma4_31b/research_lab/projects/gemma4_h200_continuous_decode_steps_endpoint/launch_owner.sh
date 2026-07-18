#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_continuous_decode_steps_endpoint
name=gemma4-continuous-decode-steps-c32-20260718t1954z
systemd-run --user --unit "$name" --collect --property=TimeoutStartSec=50min /bin/bash "$project/run_bench_owner.sh"
printf '%s\n' "$name.service"
