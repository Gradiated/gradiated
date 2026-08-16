# Codex Remote research handoff

## Mission

Determine whether model-specific vertical co-design across model representation, architecture, serving, kernels, memory hierarchy, and eventual hardware can produce a material quality-preserving reduction in SLO-compliant inference cost relative to tuned general stacks and providers such as Fireworks and Baseten.

Optimize for separate input and output token economics under long-context, prefix-heavy agent workloads. Do not build the gateway product until the opportunity is supported by reproducible measurements. Seek falsification as strongly as positive results.

## Primary projects

- `/root/workspace/research/lab`: durable simulator, validation work, business evidence, and reports.
- `/root/workspace/research/lab/experiments/glm47flash`: GLM-4.7-Flash RunPod harnesses, patches, raw evidence, and the current campaign.
- `/root/workspace/research/lab/archive`: legacy transcripts and earlier overnight artifacts. Treat these as reference material, not live Codex task state.

## Start here

Read these files before launching new compute:

1. `/root/workspace/research/lab/experiments/glm47flash/REPORT.md`
2. `/root/workspace/research/lab/experiments/glm47flash/CAMPAIGN_100_PLAN.md`
3. `/root/workspace/research/lab/CONTEXT_HANDOFF.md`
4. `/root/workspace/research/lab/docs/OVERNIGHT_REPORT_2026-07-12.md`
5. `/root/workspace/research/lab/docs/GLM_4_7_FLASH_100_DOLLAR_CAMPAIGN.md`

## Current measured state

- Native CUDA 13 SGLang BF16 successfully loaded GLM-4.7-Flash and produced deterministic greedy completions on an H100.
- The successful 16K configuration allocated a 284,098-token BF16 KV pool and captured decode CUDA graphs through batch 32.
- A valid matched throughput and dollar-per-token result has not yet been obtained, so no cost advantage has been proven.
- Repeated RunPod H100 image-start misses made additional identical placements low-value.
- The AWQ path selected CompressedTensors WNA16 Marlin after model-specific initialization fixes, then exposed fused MLA metadata and compressed `kv_b_proj` loader boundaries.
- The latest compressed `kv_b_proj` correction remains unvalidated on GPU because the prior cold load exceeded the health timeout before reaching the branch.
- The authoritative earlier campaign report records $4.11239 of initial spend. Later phase spending and artifact hashes are recorded at the top of `glm47flash/REPORT.md`.
- The prior account audit found no active GPU pods. Migration deleted the remaining exited pod record.

## Next admissible work

Reconcile the latest campaign spend and artifact ledger first. Then choose the highest-information experiment from the existing plan rather than repeating a failed placement unchanged.

The leading narrow options are:

1. Validate the compressed `kv_b_proj` correction on a cheaper 48 GB GPU with a 20-minute in-container model-health allowance while retaining the five-minute provider-startup deadline and allocation watchdog.
2. Obtain one matched native BF16 throughput baseline only when the exact CUDA 13 image is cached or provider readiness can be established without paying through repeated cold starts.
3. Evaluate a credible upstream or independently derived AWQ fused-metadata loader correction with deterministic offline tests before GPU allocation.

Every GPU experiment must declare its causal hypothesis, stock control, workload geometry, quality gate, SLO, maximum spend, timeout, artifact contract, and teardown verification before provisioning.

## Workload and economic control

- Primary agentic geometry: 8,192 input tokens and 1,024 output tokens.
- Published comparison anchor: 660.67 output tokens/s and 5,946.05 total tokens/s at concurrency 32.
- Cloudflare comparison in the campaign: $0.06/M input and $0.40/M output, equal to $0.88/M output-equivalent at an 8:1 mix.
- Campaign gate: at most $0.84/M output-equivalent at matched quality and service level.
- Strong gate: $0.60/M.
- Stretch gate: $0.40/M.

Revalidate external price anchors before making a current business claim.

## Credentials and execution

- Codex itself is authenticated with the ChatGPT subscription through `/root/.codex/auth.json`.
- `RUNPOD_API_KEY` is inherited by native Codex Remote tasks.
- `OPENAI_API_KEY` is retained in `/root/.config/gradiated/secrets.env` but is deliberately not inherited by the Codex daemon. Do not switch Codex agent usage from the subscription to API billing.
- GitHub uses the existing repository-scoped deploy key through `/root/.ssh/config`.
- Delete every RunPod pod after artifact retrieval and verify a subsequent GET returns 404.
- Never print or commit credentials.

## Durable reporting

Update `glm47flash/REPORT.md` after each allocation. Mirror decision-relevant conclusions into `gradiated/research/lab`. Label evidence as measured, analytical, vendor-reported, derived, inferred, or synthetic. Do not multiply independent optimistic improvements into a cross-stack claim without a joint executable measurement.

## Legacy state

The old custom session JSON and JSONL files are in `/root/workspace/research/lab/archive/legacy-codex-sessions`. They are an audit trail only. Native Codex uses its own task database under `/root/.codex`; importing OpenClaw databases was intentionally avoided.
