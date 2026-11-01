#!/bin/bash
# v4 pilot 2: 15 twins (no surviving replay tasks, not planted) regenerated with r31 -> reload -> lint -> twin audit ->
# synthesize 5 tasks per CLEAN/MINOR twin -> validate (validator, Opus gate, repairs) -> difficulty pilot.
O=/opt/posthog-sft/env-research/v4/pilot2
R=/opt/posthog-sft/env-research/twins_loop
T=/opt/posthog-sft/env-research/twins_reanon/traces/train.jsonl
export TWIN_V2_ROOT=$R TWIN_V2_TRACES=/opt/posthog-sft/env-research/twins_reanon/traces TWIN_V2_TAG=loop
mkdir -p $O && cd /opt/posthog-env/runner
bash /tmp/plant_dry.sh > /dev/null 2>&1   # /tmp/plant_base.jsonl: twins without surviving replay tasks
IDS=$(python3 - <<PY
import json, random
pl = {json.loads(l)["twin_id"] for l in open("/opt/posthog-sft/env-research/v4/planted1/planted.jsonl")}
tw = sorted({json.loads(l)["twin_id"] for l in open("/tmp/plant_base.jsonl")} - pl)
print(",".join(random.Random(5).sample(tw, 15)))
PY
)
echo "$IDS" > $O/twins.txt
/opt/posthog-sft/env-research/twingen/.venv/bin/python /opt/posthog-sft/env-research/twingen/v2/run_all2.py --ids "$IDS" --workers 12 --max-events 3000000 > $O/log.txt 2>&1
cd /opt/posthog-env/posthog && .venv/bin/python ../loader/load_all_v2.py --ids "$IDS" --workers 2 --force --min-free-gb 60 >> $O/log.txt 2>&1
cd /opt/posthog-env/runner
python3 - <<PY
import json
reg = {}
for line in open("/opt/posthog-env/loader/teams_v2_loop.jsonl"):
    r = json.loads(line)
    if not r.get("removed") and r.get("twin_id"):
        reg[r["twin_id"]] = r
want = set("$IDS".split(","))
seen = set()
with open("$O/base.jsonl", "w") as f:
    for l in open("/tmp/plant_base.jsonl"):
        t = json.loads(l)
        if t["twin_id"] in want and t["twin_id"] not in seen:
            seen.add(t["twin_id"]); r = reg[t["twin_id"]]
            t.update({"team_id": r["team_id"], "project_id": r.get("project_id") or r["team_id"],
                      "loaded_now_utc": r.get("loaded_now_utc"), "shift_days": r.get("shift_days")})
            f.write(json.dumps(t) + "\n")
print("base twins", len(seen))
PY
/opt/posthog-sft/env-research/twingen/.venv/bin/python /opt/posthog-sft/env-research/twingen/v2/lint.py $(for i in ${IDS//,/ }; do ls -d $R/twingen/projects_v2/$i*; done) > $O/lint.jsonl 2>>$O/log.txt
python3 v4_audit_twins.py --base $O/base.jsonl --out $O/audit --workers 6 >> $O/log.txt 2>&1
python3 v4_synth_tasks.py --base $O/base.jsonl --audit $O/audit/audit.jsonl --twins 15 --per-twin 5 --min-events 0 \
  --out $O --workers 6 >> $O/log.txt 2>&1
python3 validate_tasks.py --tasks $O/tasks.jsonl --traces $T --out $O/validated --repair --workers 8 \
  --lint $O/lint.jsonl --gate-model claude-opus-5-5 >> $O/log.txt 2>&1
python3 -c "
import json
ts=[json.loads(l) for l in open('$O/validated/validated.jsonl')]
keep=[t for t in ts if (t.get('validation') or {}).get('verdict')=='SOUND']
json.dump([t['task_id'] for t in keep], open('$O/sound_ids.json','w')); print('sound', len(keep), 'of', len(ts))" >> $O/log.txt
python3 bench_env.py --tag v4_pilot2 --tasks $O/validated/validated.jsonl --task-ids-file $O/sound_ids.json \
  --arms qwen,opus --samples 2 --arm-samples opus:1 --max-turns 12 --wall-s 1500 \
  --workers 16 --ports 18000:4,18010:4,18011:4,18012:4 --api-concurrency 4 --judge-workers 6 >> $O/log.txt 2>&1
echo PILOT2_DONE >> $O/log.txt
