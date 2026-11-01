#!/bin/bash
# v4 pilot: 10 clean train twins x 5 synthesized tasks -> validate (validator, Opus gate, repairs) -> difficulty pilot.
O=/opt/posthog-sft/env-research/v4/pilot1
L=/opt/posthog-sft/env-research/twins_loop/batches
T=/opt/posthog-sft/env-research/twins_reanon/traces/train.jsonl
mkdir -p $O
until [ "$(wc -l < /opt/posthog-sft/env-research/intent/intents.jsonl)" -ge 3600 ]; do sleep 60; done
cd /opt/posthog-env/runner
BASES=$(ls $L/b1[6-9]/validated/validated.jsonl $L/b2[0-2]/validated/validated.jsonl | tr "\n" "," | sed "s/,$//")
LINTS=$(ls $L/b1[6-9]/lint.jsonl $L/b2[0-2]/lint.jsonl | tr "\n" "," | sed "s/,$//")
python3 v4_synth_tasks.py --base "$BASES" --exclude-lint "$LINTS" --twins 10 --per-twin 5 --out $O --workers 6 > $O/synth.log 2>&1
python3 validate_tasks.py --tasks $O/tasks.jsonl --traces $T --out $O/validated --repair --workers 8 --gate-model claude-opus-5-5 >> $O/synth.log 2>&1
python3 -c "
import json
ts=[json.loads(l) for l in open('$O/validated/validated.jsonl')]
keep=[t for t in ts if (t.get('validation') or {}).get('verdict')=='SOUND']
json.dump([t['task_id'] for t in keep], open('$O/sound_ids.json','w')); print('sound', len(keep), 'of', len(ts))" >> $O/synth.log
python3 bench_env.py --tag v4_pilot1 --tasks $O/validated/validated.jsonl --task-ids-file $O/sound_ids.json \
  --arms qwen,opus --samples 2 --arm-samples opus:1 --max-turns 12 --wall-s 1500 \
  --workers 16 --ports 18000:4,18010:4,18011:4,18012:4 --api-concurrency 4 --judge-workers 6 >> $O/synth.log 2>&1
echo PILOT_DONE >> $O/synth.log
