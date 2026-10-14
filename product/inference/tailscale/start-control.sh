#!/usr/bin/env bash
set -euo pipefail
[[ -f /etc/gradiated/tailscale-control.json ]] || exit 0
if python3 - <<'CHECK'
import os, pathlib, pwd, sys
uid = pwd.getpwnam("tailscale").pw_uid
for name in os.listdir("/proc"):
    if not name.isdigit(): continue
    root = pathlib.Path("/proc") / name
    try:
        args = (root / "cmdline").read_bytes().split(b"\0")
        if root.stat().st_uid == uid and len(args) > 1 and pathlib.Path(os.fsdecode(args[0])).name == "bash" and args[1] == b"/opt/gradiated/bin/run-control":
            sys.exit(0)
    except (FileNotFoundError, ProcessLookupError): pass
sys.exit(1)
CHECK
then exit 0; fi
nohup runuser -u tailscale -- bash /opt/gradiated/bin/run-control \
  </dev/null >>/var/log/gradiated-tailscale-control.log 2>&1 &
