#!/usr/bin/env bash
set -euo pipefail
umask 077
if [[ -f /etc/gradiated/tailscale-control.json ]]; then
  bash /opt/gradiated/bin/start-control
fi
[[ -f /etc/gradiated/tailscale.json ]] || exit 0
if python3 - <<'CHECK'
import os, pathlib, sys
for name in os.listdir("/proc"):
    if not name.isdigit(): continue
    root = pathlib.Path("/proc") / name
    try:
        args = (root / "cmdline").read_bytes().split(b"\0")
        if len(args) > 1 and pathlib.Path(os.fsdecode(args[0])).name == "bash" and args[1] == b"/opt/gradiated/bin/run-tailscale":
            sys.exit(0)
    except (FileNotFoundError, ProcessLookupError): pass
sys.exit(1)
CHECK
then exit 0; fi
# tailscaled runs as root so that Tailscale SSH can open administrator shells.
nohup bash /opt/gradiated/bin/run-tailscale \
  </dev/null >>/var/log/gradiated-tailscale.log 2>&1 &
