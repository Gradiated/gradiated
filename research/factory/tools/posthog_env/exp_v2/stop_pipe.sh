#!/bin/bash
# stop only the orchestrator process itself (whole cmdline == "python3 pipeline.py", cwd exp_v2)
for pid in $(pgrep -x python3); do
  c=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null); cwd=$(readlink /proc/$pid/cwd)
  [ "$c" = "python3 pipeline.py " ] && [ "$cwd" = "/opt/posthog-env/exp_v2" ] && kill $pid && echo "stopped orchestrator $pid"
done
