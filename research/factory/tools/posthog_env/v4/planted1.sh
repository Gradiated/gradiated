#!/bin/bash
# v4 planted round: plant 15 twins (no surviving replay tasks), regenerate + reload, then (after pilot 1) synthesize
# 3 tasks per planted twin (one investigation built on the planted change), validate, difficulty pilot.
O=/opt/posthog-sft/env-research/v4/planted1
R=/opt/posthog-sft/env-research/twins_loop
T=/opt/posthog-sft/env-research/twins_reanon/traces/train.jsonl
export TWIN_V2_ROOT=$R TWIN_V2_TRACES=/opt/posthog-sft/env-research/twins_reanon/traces TWIN_V2_TAG=loop
mkdir -p $O && cd /opt/posthog-env/runner
bash /tmp/plant_dry.sh > /dev/null 2>&1   # refreshes /tmp/plant_base.jsonl (twins without surviving tasks)
python3 v4_plant_scenarios.py --tasks /tmp/plant_base.jsonl --twins 15 --out $O --seed 21 > $O/log.txt 2>&1
CH=$(python3 apply_overrides.py --overrides-dir $O/overrides --root $R)
echo "changed: $CH" >> $O/log.txt
/opt/posthog-sft/env-research/twingen/.venv/bin/python /opt/posthog-sft/env-research/twingen/v2/run_all2.py --ids "$CH" --workers 12 --max-events 3000000 >> $O/log.txt 2>&1
cd /opt/posthog-env/posthog && .venv/bin/python ../loader/load_all_v2.py --ids "$CH" --workers 2 --force --min-free-gb 60 >> $O/log.txt 2>&1
cd /opt/posthog-env/runner
python3 - <<PY
import json
reg = {}
for line in open("/opt/posthog-env/loader/teams_v2_loop.jsonl"):
    r = json.loads(line)
    if not r.get("removed") and r.get("twin_id"):
        reg[r["twin_id"]] = r
pl = [json.loads(l) for l in open("$O/planted.jsonl")]
seen = set()
with open("$O/base.jsonl", "w") as f:
    for l in open("/tmp/plant_base.jsonl"):
        t = json.loads(l)
        if t["twin_id"] in {p["twin_id"] for p in pl} and t["twin_id"] not in seen:
            seen.add(t["twin_id"]); r = reg[t["twin_id"]]
            t.update({"team_id": r["team_id"], "project_id": r.get("project_id") or r["team_id"],
                      "loaded_now_utc": r.get("loaded_now_utc"), "shift_days": r.get("shift_days")})
            f.write(json.dumps(t) + "\n")
print("planted twins ready", len(seen))
PY
echo PLANTED_LOADED >> $O/log.txt
until grep -q PILOT_DONE /opt/posthog-sft/env-research/v4/pilot1/synth.log 2>/dev/null; do sleep 60; done
python3 v4_synth_tasks.py --base $O/base.jsonl --planted $O/planted.jsonl --only-planted --twins 15 --per-twin 3 \
  --min-events 0 --out $O --workers 6 >> $O/log.txt 2>&1
python3 validate_tasks.py --tasks $O/tasks.jsonl --traces $T --out $O/validated --repair --workers 8 --gate-model claude-opus-5-5 >> $O/log.txt 2>&1
python3 -c "
import json
ts=[json.loads(l) for l in open('$O/validated/validated.jsonl')]
keep=[t for t in ts if (t.get('validation') or {}).get('verdict')=='SOUND']
json.dump([t['task_id'] for t in keep], open('$O/sound_ids.json','w')); print('sound', len(keep), 'of', len(ts))" >> $O/log.txt
python3 bench_env.py --tag v4_planted1 --tasks $O/validated/validated.jsonl --task-ids-file $O/sound_ids.json \
  --arms qwen,opus --samples 2 --arm-samples opus:1 --max-turns 12 --wall-s 1500 \
  --workers 16 --ports 18000:4,18010:4,18011:4,18012:4 --api-concurrency 4 --judge-workers 6 >> $O/log.txt 2>&1
echo PLANTED_DONE >> $O/log.txt
