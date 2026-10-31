#!/bin/bash
# Held-out eval set: the test split rebuilt through the current pipeline (curate, validate, Opus gate, regeneration).
E=/opt/posthog-env/exp_v2
IDS=$(python3 -c "import json;print(','.join(json.loads(l)['id'] for l in open('/opt/posthog-sft/env-research/twins_reanon/traces/test_v2.jsonl')))")
cd /opt/posthog-env/runner
python3 loop_producer.py --rebuild-ids "$IDS" --name eval_v2 --split test_v2
B=/opt/posthog-sft/env-research/twins_loop/batches/eval_v2
python3 loop_producer.py --refresh-teams $B/validated/validated.jsonl
python3 - <<PY
import json
ts = [json.loads(l) for l in open("$B/validated/validated.jsonl")]
keep = [t for t in ts if not t.get("exclude") and (t.get("validation") or {}).get("verdict") == "SOUND"]
with open("$E/eval_tasks.jsonl", "w") as f:
    for t in keep:
        f.write(json.dumps(t, ensure_ascii=False) + "\n")
json.dump([t["task_id"] for t in keep], open("$E/eval_ids.json", "w"))
print("eval tasks", len(keep), "of", len(ts))
PY
