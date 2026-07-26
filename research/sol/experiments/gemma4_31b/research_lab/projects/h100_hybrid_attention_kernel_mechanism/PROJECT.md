# H100 hybrid attention kernel mechanism

## Decision question

Is there one concrete source-level H100 paged-attention dataflow change for Gemma 4 31B's five-local/one-global hybrid geometry that can plausibly save at least 5% whole-request cost at the campaign workload and be falsified by a small checkpoint-free exact-shape measurement?

This is a materially different `$0` mechanism project while the L40S direct-FP8 owner runs. It must not poll/edit/wait for that owner, query or mutate a provider, invoke CUDA, pull an image, transfer a checkpoint, or claim H100 throughput. It refines the completed hardware frontier's generic “fused paged hybrid attention” label into a causal source/chip hypothesis or closes it.

## Evidence and scope

Start from `../gemma4_hardware_kernel_frontier/FRONTIER.json`, the exact Gemma geometry, `h200_c32_prefill_peak_compute_floor`, `h200_bf16_kv_attention_bandwidth_floor`, and the invalid-attention audit/terminal. Inspect the pinned vLLM hybrid/paged-attention source and relevant shared accelerator inventory. Trace a concrete chain:

1. exact local/global query/KV/page geometry and architecture multiplicities;
2. current pinned source call/dataflow and compulsory bytes/launches;
3. H100 SM/L2/HBM/tensor-core or shared-memory constraint actually limiting it;
4. one precise scheduling, tiling, page reuse, precision, or fusion change;
5. one checkpoint-free measurement that distinguishes the proposed limiter from compute, launch, and bandwidth alternatives.

Reject dense-varlen stand-ins, scalar-window mistakes, global 358x aggregation, unbound “custom attention,” and any claimed transfer from H200/L40S. Quantify the maximum whole-request effect against the H100 planning hurdle `1.8249 completed requests/s`; close the branch if the mechanism cannot reach 5% even optimistically. Return either a content-bound exact-shape discriminating measurement contract (not a provider launcher) or typed none. Do not create a successor project or duplicate the active linears experiment.

## Budgets

- Wall clock: 30 minutes.
- Compute: 3 local CPU-hours; no GPU.
- Storage: 512 MiB retained plus 256 MiB temporary.
- Spend: `$0`; no provider, image pull, checkpoint, compilation, or external mutation.

Write concise `MECHANISM.json`, update log/status, and terminalize.

## Director readmission — 2026-07-26

The analytical mechanism remains retained, but the separate v2 execution
packet was correctly rejected before spend. Consume
`DIRECTOR_EXECUTION_EQUIVALENT_READMISSION_20260726.json` and its hash-bound
audit. Implement one fresh project-local, execution-equivalent program and
fail-closed evaluator for the pinned native paged-KV producer/consumer path.
This cycle ends at a typed source-readiness terminal; it must not query,
create, claim, or use a provider GPU. Working source and narrow tests are the
decision evidence—another plan or audit-only successor is not.
