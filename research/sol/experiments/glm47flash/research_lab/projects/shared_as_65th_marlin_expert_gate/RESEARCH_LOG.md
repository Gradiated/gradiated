# Research log

## 2026-07-16 — Director opening handoff

Use the freed exact-MoE slot on a semantics-preserving shared/sparse fusion rather than another sorting or padding proxy. Append one weight-1 shared assignment/token as physical expert 65 in the stock sorted W4 Marlin path, preserve the four routed assignments, and prove exact reduction plus kernel legality. Close unless timestamped or conservative dependency evidence identifies enough removable sequential shared-branch wall time to matter after a future official-W4 full47 endpoint.

## 2026-07-16 — MECHANISM_CLOSE

Question/action: bind the 65th stock-Marlin expert, prove appended-descriptor semantics, and derive a conservative sequential-wall ceiling at zero spend.

Evidence: `run_gate.py` is a deterministic stdlib-only fixture bound to the retained GLM source at `../sglang_current_awq_runtime_gate/evidence/glm4_moe_lite.py:180-229`, where fused construction uses `num_experts = routed + shared` and `top_k = routed_top_k + shared`. It appends physical expert ID 64 and weight 1.0 to every token while preserving the four routed IDs/weights, then validates balanced, duplicate, empty, and skewed cases. All cases have exact float32 separate-vs-appended SwiGLU/down/reduction equality. The stock alignment model adds one expert block of 64 padded rows at c16 (16 shared rows) and c32 (32 shared rows), with 16/32 additional descriptors; K=2048 and gate/up/down N dimensions are 128-tile multiples, so the extra slot does not introduce a scalar fallback or illegal SM89 shape.

Trace evidence: retained V24R2/V25R1 decode traces are hash-bound in `artifacts/SHARED_65TH_GATE.json`. Their explicitly shared residual signatures are 0.3844168% and 0.4477436% of summed decode kernel duration. The bound credits only the smaller 0.3844168% as removable sequential wall time; it does not credit unassigned standard-Marlin work or overlapping summed kernel time. Applying the perfect-fusion bound to the retained 535.286 tok/s control gives 537.3518 tok/s, below the 606.355 tok/s gate (and below any future full47 baseline that would need to reach that gate).

Interpretation/next move: `MECHANISM_CLOSE`. The representation and arithmetic mechanism survives, but the measured/retained wall-time opportunity is too small to nominate fusion alone. Reopen only with an official-W4 full47 baseline and timestamped source/trace attribution showing substantially larger sequential shared-branch ownership.

## 2026-07-16 — Director evidence correction

The `0.3844%` retained signature is a share of summed kernel duration, not source-timestamped removable sequential wall, and the fixture did not execute an actual 65-expert WNA16 kernel. Therefore `537.352 tok/s` is not a defensible measured endpoint bound. The close still follows from the contract's missing sequential attribution. Reconsider only as an already-staged adjacent arm if a scope-compatible endpoint is near `604.02 tok/s`, or if new timestamped evidence establishes more removable wall.

## 2026-07-16 — Director direct component reopen

The later exact unchanged-stock c32 endpoint is `609.606365 tok/s`, so the explicit `604.02 tok/s` conditional-reopen threshold is met. After the invalid FP8 owner cleans to authenticated zero inventory, run one direct real-WNA16 complete-MoE component A/B: stock 64 routed experts plus separate exact BF16 shared branch versus the same official group32 W4 weights with the shared branch executed as physical expert 65 at weight 1. Require `>=1.63x`, exact semantics/numerics, kernel/resource identity, and p50/p95 evidence. One L40S create, `$0.55`/1,800 seconds, no fallback/retry/readiness return/retention; always clean.

## 2026-07-16 — Director contract correction and release

Cleanup is authenticated zero, but source audit corrects the direct contract before launch. Exact semantics are `1.8 * normalized_top4_routed + shared`; B must therefore pass descriptor weights `[1.8*w0..1.8*w3,1.0]` with no outer scale. Pinned stock already overlaps its BF16 shared MLP on an auxiliary stream at c32, so A0 must time that actual wall path, not sequential kernels. Add A1 as the identical official-W4 shared payload executed separately through native WNA16 with overlap; B fuses those exact bytes as expert 64. Runtime block size is 8 and the 32 shared rows have zero padding, superseding the old block-64 proxy. Freeze/test the one-layer payload, benchmark, and teardown-preseeded wrapper, then launch in the same turn; no readiness result or retained arm.

## 2026-07-16 — Director endpoint audit: operational null, cleanup only

The foreground controller died after creating `computeinstance-e00bwz6fs4z3sa3dme`; only the independent cleanup watchdog remains, with deadline `2026-07-16T14:54:34Z`. Read-only inspection found an idle GPU, no pulled image, staged input, remote result, or archive, so useful and scored GPU science are both zero. This is `ORPHANED_OWNER_PRE_SCIENCE_PENDING_CLEANUP`, consumes the one-create/no-retry contract, and leaves the mechanism scientifically untested rather than falsified.

Reject any hypothetical pass from the frozen packet: it computes `silu(gate*up)` rather than `silu(gate)*up`, copies A0 weights CPU-to-CUDA inside timed calls, does not invoke the pinned stock `SharedFusedMoE` comparator, misbinds E64 arms to 65 global experts, fixes arm order, omits duplicate/empty route cases, and lacks kernel/grid/workspace profiling. Permit only watchdog teardown followed by independent zero-inventory authentication; no retry, recovery, or successor in this lineage.

## 2026-07-16 — Watchdog cleanup terminal

The independent watchdog exited after its `2026-07-16T14:54:34.362751Z` deadline. A fresh authenticated inventory at `14:55:38Z` returned zero instances and zero disks. No SSH/bootstrap/result/summary event was ever written, so useful and scored GPU science remain zero. Provider creation at `14:24:34.535582Z` to the watchdog deadline gives a derived `1,799.827168 s` exposure and `$0.379424665` at the measured `$0.7589222/h` VM-plus-disk rate. Close `ORPHANED_OWNER_PRE_SCIENCE_CLOSE`; no retry or mechanism claim.
