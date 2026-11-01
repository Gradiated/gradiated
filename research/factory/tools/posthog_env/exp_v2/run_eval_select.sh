#!/bin/bash
# Eval selection after the eval_v2 build: final SOUND plus GATE_MINOR (usable with a harmless flaw, same for every arm);
# the strictly gated subset is listed separately (eval_ids_strict.json). Then the baselines.
E=/opt/posthog-env/exp_v2
B=/opt/posthog-sft/env-research/twins_loop/batches/eval_v2
until [ -f $B/READY ]; do sleep 60; done
cd /opt/posthog-env/runner
python3 loop_producer.py --refresh-teams $B/validated/validated.jsonl
python3 - <<PY
import json
ts = [json.loads(l) for l in open("$B/validated/validated.jsonl")]
ok = {"SOUND", "GATE_MINOR"}
keep = [t for t in ts if (t.get("validation") or {}).get("verdict") in ok]
with open("$E/eval_tasks.jsonl", "w") as f:
    for t in keep:
        f.write(json.dumps(t, ensure_ascii=False) + "\n")
json.dump([t["task_id"] for t in keep if (t.get("validation") or {}).get("verdict") == "SOUND"], open("$E/eval_ids_strict.json", "w"))
json.dump([t["task_id"] for t in keep], open("$E/eval_ids.json", "w"))
print("eval tasks", len(keep), "strict", sum(1 for t in keep if t["validation"]["verdict"] == "SOUND"), "of", len(ts))
PY
exec python3 bench_env.py --tag ev2_baselines --tasks $E/eval_tasks.jsonl --task-ids-file $E/eval_ids.json \
  --arms qwen,opus --samples 3 --arm-samples opus:1 --max-turns 12 --wall-s 1500 \
  --workers 16 --ports 18000:4,18010:4,18011:4,18012:4 --api-concurrency 4 --judge-workers 6
