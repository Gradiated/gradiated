#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)

python3 "$root/later_pair_workload.py" \
  --concurrency 32 \
  --identity "$root/packet/C32_WORKLOAD.json"
python3 "$root/later_pair_workload.py" \
  --concurrency 48 \
  --identity "$root/packet/C48_WORKLOAD.json"

python3 - "$root/L40S_DUAL_KV4_C48_SATURATION_OFFLINE_TERMINAL.json" <<'PY'
import json
import sys

terminal = json.load(open(sys.argv[1]))
later = terminal["later_measurement"]
if later["type"] != "none":
    raise SystemExit("terminal unexpectedly authorizes a later measurement")
print(later["reason"])
raise SystemExit(78)
PY
