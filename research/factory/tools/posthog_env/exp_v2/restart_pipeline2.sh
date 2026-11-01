#!/bin/bash
# Restart the orchestrator after the Opus re-run AND the running trainings (ev2-dagger, ev2-combo) are done.
E=/opt/posthog-env/exp_v2
while pgrep -f "bench_env.py --tag tr2_data" > /dev/null || pgrep -f "sh train.sh" > /dev/null; do sleep 60; done
cd $E && exec python3 pipeline.py
