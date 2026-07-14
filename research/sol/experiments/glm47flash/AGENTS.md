# Research instructions

Read `CODEX_REMOTE_HANDOFF.md`, `REPORT.md`, and `CAMPAIGN_100_PLAN.md` before changing an experiment or allocating a GPU.

Run the campaign autonomously to its campaign-level decision or authorized budget/time limit. Do not pause for user confirmation after capacity misses, startup failures, runtime defects, negative measurements, or an individual lineage's stop rule. Record the result, falsify the current explanation, and select the cheapest materially different experiment that can advance the campaign objective.

Use `RUNPOD_API_KEY` directly whenever RunPod is in scope. Explore live inventory and adapt datacenter, cloud class, GPU SKU, runtime, representation, image strategy, or workload geometry when scientifically admissible. Do not repeat a failed placement unchanged, but do not confuse exhausted placement for one SKU/datacenter with exhaustion of the campaign. Prefer automatic cleanup and continuation over asking the user to inspect or operate provider resources.

Only ask the user when the next useful action needs authority not already granted, would exceed the campaign cap, is destructive or irreversible outside disposable experiment resources, requires unavailable credentials, materially expands the campaign, or creates a safety/legal risk. An inconvenient, expensive, uncertain, or non-ideal next experiment is not by itself a blocker if it remains within the preregistered cap and objective.

Prefer falsifiable, single-cause experiments with a stock control. Record workload geometry, quality gate, SLO, spend cap, timeout, artifact hash, and verified teardown. Do not claim throughput, quality, or cost improvements without matching measured evidence.

Use `RUNPOD_API_KEY` from the environment. Never print or commit secrets. Delete every created pod after artifact retrieval and verify it no longer exists.

Keep durable conclusions in `REPORT.md` and mirror business-relevant findings into `/root/workspace/research/sol`.
