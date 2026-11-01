#!/bin/bash
# dry run: plans for twins whose replay tasks did not survive (planting changes a twin's data)
L=/opt/posthog-sft/env-research/twins_loop/batches
python3 - <<PY
import json, glob
reg = {}
for line in open("/opt/posthog-env/loader/teams_v2_loop.jsonl"):
    r = json.loads(line)
    if not r.get("removed") and r.get("twin_id"):
        reg[r["twin_id"]] = r
sound = set()
rows = []
for f in sorted(glob.glob("$L/b1[6-9]/validated/validated.jsonl") + glob.glob("$L/b2[0-2]/validated/validated.jsonl")):
    for l in open(f):
        t = json.loads(l)
        if (t.get("validation") or {}).get("verdict") == "SOUND":
            sound.add(t["twin_id"])
        rows.append(t)
with open("/tmp/plant_base.jsonl", "w") as f:
    for t in rows:
        r = reg.get(t["twin_id"])
        if t["twin_id"] in sound or not r or (r.get("events") or 0) < 30000:
            continue
        t.update({"team_id": r["team_id"], "loaded_now_utc": r.get("loaded_now_utc"), "shift_days": r.get("shift_days")})
        f.write(json.dumps(t) + "\n")
print("plant base tasks", sum(1 for _ in open("/tmp/plant_base.jsonl")))
PY
cd /opt/posthog-env/runner && rm -rf /tmp/plant_dry && python3 v4_plant_scenarios.py --tasks /tmp/plant_base.jsonl --twins 4 --out /tmp/plant_dry --seed 3
python3 -c "
import json
for l in open('/tmp/plant_dry/planted.jsonl'):
    p=json.loads(l); print(p['event'][:30], list(p['where'])[0], 'share', p['segment_share'], p['from'], p['to'], 'x', p['factor'], 'base/day', p['baseline_daily'])"
