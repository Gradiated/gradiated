#!/bin/bash
# Re-run the Opus arm (all 82 capture rollouts failed: the capture file's directory did not exist yet).
E=/opt/posthog-env/exp_v2
R=/opt/posthog-env/runner/bench/tr2_data
rm -rf $R/opus $E/data/opus $E/data/opus_keep.txt /opt/posthog-env/opd_env/rollouts/ev2opus
cd /opt/posthog-env/runner
exec python3 bench_env.py --tag tr2_data --capture --tasks $E/train_tasks.jsonl --task-ids-file $E/train_ids.json \
  --arms opus --samples 1 --max-turns 12 --wall-s 1500 --api-concurrency 6 --workers 6 --judge-workers 6
