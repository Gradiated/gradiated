#!/bin/bash
# Baselines on the held-out eval set: base Qwen x3 + Opus x1 (different teams from the train pool).
E=/opt/posthog-env/exp_v2
until [ -f $E/eval_ids.json ]; do sleep 60; done
cd /opt/posthog-env/runner
exec python3 bench_env.py --tag ev2_baselines --tasks $E/eval_tasks.jsonl --task-ids-file $E/eval_ids.json \
  --arms qwen,opus --samples 3 --arm-samples opus:1 --max-turns 12 --wall-s 1500 \
  --workers 16 --ports 18000:4,18010:4,18011:4,18012:4 --api-concurrency 4 --judge-workers 6
