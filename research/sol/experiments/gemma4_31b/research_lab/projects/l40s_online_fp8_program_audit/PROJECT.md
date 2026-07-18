# L40S online-FP8/W4 staged-program audit

## Decision question

Do the immutable bytes captured by the live `l40s_online_fp8_actual_consumer_floor` owner behaviorally implement the admitted actual-consumer experiment and conditional W4 arm, or must their science be quarantined?

This is an independent `$0`, read-only advisory audit after provider creation. It cannot edit or authorize the paid project, stop/restart/signal its owner or watchdog, query/mutate provider, invoke CUDA, or substitute for typed cleanup.

## Required audit

Inspect the paid brief, identity assertion, `fp8_actual.py`, `w4_actual.py`, `remote_stage.sh`, owner/launcher, final audit/precreate/request/events, and exact transitive files/hashes captured by the live process. Audit behavior, not substring assertions:

- genuine current-image `Fp8LinearMethod` online producer/process/apply and actual FP8 KV writer, with valid vLLM config context and no direct generic fallback;
- all six exact shapes, M=12/M=14 decode and 3,679 prefill plus separate 8,730 sensitivity; actual BF16 comparators/head and exact layer/request aggregation without double division;
- nontrivial deterministic data, numerical oracle that consumes timed output, finite/tolerance enforcement, raw CUDA/wall stability, allocator/HBM/power/utilization telemetry;
- exact KV writer geometry/scale semantics and disjoint accounting; no attention/KV read double count;
- W4 program fully staged before create and actual AWQMarlin producer/consumer; trigger requires valid nonzero FP8 science, residual condition, ten-minute readiness/headroom and same retained owner, while invalid FP8 tears down;
- one allocation/no repair/budgets, immutable transitive lifecycle snapshot, durable owner plus independent watchdog, typed atomic retrieval, exposure/cost accounting and authenticated cleanup.

Write `AUDIT.json` with exact line/file/hash evidence and `pass_advisory`, `fail_quarantine_science`, or `insufficient_immutable_evidence`. A failure must not mutate the live owner; it guides later interpretation only.

## Budgets

- Wall clock: 15 minutes.
- Compute: 1 local CPU-hour; no GPU.
- Storage: 128 MiB retained plus 64 MiB temporary.
- Spend: `$0`; provider access/mutation forbidden.
