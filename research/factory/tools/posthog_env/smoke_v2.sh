#!/bin/bash
# Smoke-test v2 tasks end to end: one base-Qwen rollout per task id (vLLM :18012, --reset-team-state, all turns).
# Local docs search on (POSTHOG_LOCAL_DOCS=1).
# Usage: smoke_v2.sh ID[,ID...]   (2 concurrent; transcripts in runner/runs_v2/smoke/)
cd /opt/posthog-env/posthog
mkdir -p ../runner/runs_v2/smoke ../runner/logs/smoke_v2
echo "$1" | tr , "\n" | xargs -P 2 -I{} sh -c 'POSTHOG_LOCAL_DOCS=1 VLLM_BASE_URL=http://127.0.0.1:18012/v1 timeout 1100 .venv/bin/python ../runner/run_task.py --tasks ../runner/tasks/v2/test.jsonl --task-id {} --model qwen --out ../runner/runs_v2/smoke/{}.json --max-turns 0 --wall-s 900 --reset-team-state > ../runner/logs/smoke_v2/{}.log 2>&1; tail -1 ../runner/logs/smoke_v2/{}.log'
echo SMOKE_DONE
