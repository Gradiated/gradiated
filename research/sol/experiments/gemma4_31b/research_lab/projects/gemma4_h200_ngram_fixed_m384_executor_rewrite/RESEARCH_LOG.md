# Research log

## 2026-07-25 — admitted

This lane is admitted as the second genuine 20%-class bet alongside DFlash.
It is not another mask or scheduler micro-optimization: the required output is
an exact fixed-M384 target-forward executor implementation and measurement.
Offline source/trace work starts immediately; H200 work queues behind the
independent live DFlash owner.

## 2026-07-25 — bound trace resolved; executor packet ready behind DFlash

Question: does the persisted c32 trace leave enough non-overlapping
target-forward time for the 20% objective, and which exact recurring boundary
should receive the one implementation?

Action: verified all nine `EVIDENCE_BINDING.json` hashes, materialized the
exact trace and runtime sources project-locally, reconstructed the request and
verification union, and froze a guarded H200 c32/M384/max-extend-12
`BLOCK_M=8` attention overlay. Added the actual stock/candidate
`extend_attention_fwd` consumer, CUDA-graph replay oracle, four-launch NCU
consumer, matched c32 endpoint pair, immutable packet, and retained-claim
owner. The experiment contract is `EXPERIMENT_CONTRACT.json`.

Evidence: `artifacts/BOUND_CRITICAL_PATH.json` (`bcc523eb...`) binds 15 exact
M384 cycles. Counter-derived full-request target verification is
`0.158548-0.180858 s/request`, or `25.36-28.93%` of the qualified
`0.625149 s/request` baseline. Reaching `0.500119 s/request` therefore needs
`69.13-78.86%` target-boundary reduction. Attention contributes
`1.488206 s` of the `2.216848 s` captured GPU union (`67.13%`), with 750 local
and 150 global launches, 255 registers/thread, and stock 64/32-row tiles for
12 useful rows. The eight-row tensor-core shape compiled for SM90 in the
pinned Triton 3.6.0 image; actual candidate execution remains unconsumed.

Interpretation: the complete target-forward 20% ceiling is physically open
but narrow and demands a large boundary win. Attention is 67.13% of that
target GPU union, so even eliminating the entire family would save only
17.03-19.42% of a qualified request. The implemented attention candidate is
therefore stackable-only; it cannot independently establish the 20% campaign
objective. It remains a causal, fixed-geometry test of padded
query/live-accumulator waste, not a replay of the rejected 1x2x1 FP8 cluster,
BLOCK_M=16/32 tree candidates, masks, penalties, or allocator work.

Terminal: `FIXED_M384_EXECUTOR_OFFLINE_RESULT.json` records the required
source-complete offline result. The protected H200 remains claimed by live
priority-8490 `gemma4_h200_dflash_endpoint` owner PID 841139, and the current
director binding explicitly forbids GPU or remote-bench access. After DFlash
releases, the director must consume the offline result, decide whether this
stackable-only candidate remains competitive, and explicitly bind a paid
execution plus lifecycle/watchdog before any claim. Current project provider
spend remains `$0`.
