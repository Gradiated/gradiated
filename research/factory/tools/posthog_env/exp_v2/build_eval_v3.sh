#!/bin/bash
# Eval v3: the 400-conversation holdout (by project cluster, stratified toward moderate/hard), built in two halves.
cd /opt/posthog-env/runner
H=/opt/posthog-sft/env-research/twins_loop/eval_holdout.json
A=$(python3 -c "import json;print(','.join(json.load(open('$H'))['ids'][:200]))")
B=$(python3 -c "import json;print(','.join(json.load(open('$H'))['ids'][200:]))")
python3 loop_producer.py --rebuild-ids "$A" --name eval_v3a
python3 loop_producer.py --rebuild-ids "$B" --name eval_v3b
echo EVAL_V3_DONE
