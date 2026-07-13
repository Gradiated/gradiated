# Research instructions

Read `CODEX_REMOTE_HANDOFF.md`, `REPORT.md`, and `CAMPAIGN_100_PLAN.md` before changing an experiment or allocating a GPU.

Prefer falsifiable, single-cause experiments with a stock control. Record workload geometry, quality gate, SLO, spend cap, timeout, artifact hash, and verified teardown. Do not claim throughput, quality, or cost improvements without matching measured evidence.

Use `RUNPOD_API_KEY` from the environment. Never print or commit secrets. Delete every created pod after artifact retrieval and verify it no longer exists.

Keep durable conclusions in `REPORT.md` and mirror business-relevant findings into `/root/workspace/research/sol`.
