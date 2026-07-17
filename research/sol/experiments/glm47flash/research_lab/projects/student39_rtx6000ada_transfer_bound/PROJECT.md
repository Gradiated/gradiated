# 39-layer student RTX 6000 Ada transfer bound

## Question

Does the measured 39-layer L40S student create a robust sustainable-cost path on the closest 48-GiB Ada workstation twin, RTX 6000 Ada, strong enough to preserve as the leading post-quality production-placement candidate?

## Why it matters

The student measured `734.557` output tok/s at c32 and `$0.415973/M` at `$1.10/L40S-hour`, but sustainable L40S economics have limited lifecycle/utilization margin. RTX 6000 Ada shares SM89, 142 SMs, 568 Tensor Cores, 96 MiB L2, and 48 GiB with L40S; its 960 GB/s memory bandwidth is above L40S's 864 GB/s, while its 300-W power limit is below 350 W. The earlier full-model transfer screen bounded retained throughput at `0.821–0.990x` and found a same-day `$0.77/hour` listing, conservatively `$0.847/hour` after a 10% lifecycle allowance. That full-model conclusion does not answer the now-measured, smaller student.

At `$0.847/hour`, the campaign's `$0.514/M` gate requires `457.739` output tok/s. Relative to measured student c32, that is only `0.623x` retention; applying the prior full-model `0.821x` floor would imply about `603` tok/s, but this multiplication is an analytical prior, not measured student evidence.

## Fixed evidence

- Student measurement: `../distilled_depth_student_architecture/artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02/summary.json`, artifact SHA-256 `f9f3f77da53d30e87604d8a0f8c1ddd81e8bed65bab100896b06b5c6a7b35383`.
- Student c16/c24/c32: `674.424 / 661.661 / 734.557` output tok/s; exact cache-off 8,192-input/1,024-output workload; measured c32 TTFT p99 `16.568s`, TPOT p99 `39.669ms`, wall `89.218s` for 64 requests.
- Corrected student c32 analytical peak/headroom: `44,459.517 / 1,608.483 MiB`; terminal telemetry reports about 43.665 GiB during work. Reconcile units and card-visible capacity rather than choosing the favorable number.
- Prior hardware/economic evidence: `../rtx6000ada_transfer_bound/`, especially its transfer artifact and same-day RunPod listing. Reuse it; do not perform another general price search or treat an experimental marketplace listing as a committed production quote.

## Scope

Run one zero-provider, no-CUDA bound. Rebind the prior chip transfer model to the exact 39-layer measured profiles and physical checkpoint: W4/BF16 bytes, KV at c16/c24/c32, SM/tile identity, memory bandwidth, clocks/power, thermal sustained behavior, card-visible memory, runtime/driver compatibility, and the exact vLLM compressed-tensors path. Separate invariants that transfer because both chips are SM89 from differences that need measurement. Quantify retained-throughput and capacity break-even at c16 and c32 under the `$0.77/hour` listing, the conservative `$0.847/hour` experimental lifecycle rate, and a sensitivity range; calculate required productive utilization and maximum lifecycle overhead for `$0.514/M`.

Do not multiply independent optimistic bounds into a measured result. Do not refresh unrelated prices, invoke RunPod, allocate a GPU, edit the launcher, run quality, or claim a production rate from an on-demand listing. Determine whether one later RTX 6000 Ada c32 arm would be scientifically decisive after quality recovery, and specify its exact runtime/workload, minimum throughput, memory, reliability, spend, and cleanup gates. Nominate at most one later arm only if c32 admission is robust and the conservative retention/economics remain materially below the target. Otherwise close this placement at `$0`.

## Artifact contract

Produce `STUDENT39_RTX6000ADA_BOUND.json`, `student39_rtx6000ada_bound.py`, and `RESEARCH_LOG.md`, with exact evidence hashes and measured/analytical/vendor-listed/inferred labels.

## Available resources

Use the two existing project trees, exact student checkpoint/manifests, `hardware/L40S.md`, shared factory tools, and campaign telemetry. The shared price inventory and same-day RTX listing evidence are fresh enough for this bound.
