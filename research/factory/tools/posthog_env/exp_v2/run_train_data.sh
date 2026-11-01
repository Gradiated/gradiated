#!/bin/bash
# Train pool = final SOUND tasks of loop rounds b16-b22; data = base Qwen x4 + Opus x1 (captured) in one bench process
# (per-team lock), then the DAgger correction loop on the same teams.
E=/opt/posthog-env/exp_v2
L=/opt/posthog-sft/env-research/twins_loop/batches
until [ -f $L/b22/READY ]; do sleep 60; done
python3 - <<PY
import json, os
seen, keep = set(), []
for b in ("b22", "b21", "b20", "b19", "b18", "b17", "b16"):
    f = f"$L/{b}/validated/validated.jsonl"
    if not os.path.exists(f):
        continue
    for l in open(f):
        t = json.loads(l)
        if t.get("exclude") or (t.get("validation") or {}).get("verdict") != "SOUND" or t["conversation_id"] in seen:
            continue
        seen.add(t["conversation_id"]); t["source_batch"] = b; keep.append(t)
with open("$E/train_tasks.jsonl", "w") as f:
    for t in keep:
        f.write(json.dumps(t, ensure_ascii=False) + "\n")
print("train tasks", len(keep))
PY
cd /opt/posthog-env/runner
python3 loop_producer.py --refresh-teams $E/train_tasks.jsonl
python3 -c "import json;json.dump([json.loads(l)['task_id'] for l in open('$E/train_tasks.jsonl')],open('$E/train_ids.json','w'))"
python3 bench_env.py --tag tr2_data --capture --tasks $E/train_tasks.jsonl --task-ids-file $E/train_ids.json \
  --arms qwen,opus --samples 4 --arm-samples opus:1 --max-turns 12 --wall-s 1500 \
  --workers 30 --ports 18000:6,18010:6,18011:6,18012:6 --api-concurrency 6 --judge-workers 8
mkdir -p $E/dagger
cd /opt/posthog-env/correct
export LOOP_JUDGE=v3h LOOP_NOTES_FILE=$E/train_tasks.jsonl
python3 loop.py --tasks $E/train_tasks.jsonl --root $E/dagger --rounds 3 \
  --thresh 7.5 --max-turns 12 --wall-s 1500 --workers 16 --ports 18000:4,18010:4,18011:4,18012:4 --reset-team-state track \
  > $E/dagger.log 2>&1
touch $E/dagger/DONE
