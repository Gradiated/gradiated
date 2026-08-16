# SGLang v0.5.12 H200 stock concurrency frontier

## Question

Can the exact economically passing Gemma 4 31B SGLang/H200 candidate reduce complete-request service time materially at c64, and does memory/throughput headroom justify a conditional c96 arm?

## Why this matters

The bound stock c32 run is the campaign's first full-stack market pass: 32/32 exact 4,214-input/358-output requests, `2.7525220286 requests/s`, and `0.3633031778 s/request` against the strict `0.4720118230` ceiling. Its scored batch took only about 11.6 seconds after roughly 49 minutes of checkpoint, image, and readiness setup. The campaign allows background latency, so higher concurrency on the same resident checkpoint/image/server stack is the shortest path to a stronger cost frontier. This performance question is independent of the active paired-quality capture, but GPU execution is gated on that project's typed text-only quality pass.

## Bound identity and comparator

Use `BINDINGS.json`; do not substitute a checkpoint, image, runtime, trace, tokenizer, KV dtype, or accelerator. The comparator is the reconciled c32 terminal with `0.3633031778124973 s/request`, `2.7525220286295027 requests/s`, 32/32 complete requests, and valid token accounting. The campaign economic gate remains `0.47201182295214134 s/request` (`2.118591 requests/s`).

## Scope and execution order

Prepare the exact runner and artifact contract locally while the quality project owns the bench. Do not poll, wait for, attach to, or mutate its claim. Do not create or destroy provider resources.

GPU work is admitted only after both conditions hold:

1. `sglang_v0512_h200_stock_quality_validation` emits a typed paired-quality pass for text-only, default non-reasoning use.
2. A director-owned H200 bench is released and its resident model, revision, checkpoint, immutable image, SGLang runtime, FP8-E5M2 KV configuration, and exact workload identity match `BINDINGS.json`.

Claim that compatible bench atomically. Run one c64 complete-request arm first, preserving the exact request bytes and generation contract. Require 64 complete, nonempty, failure-free requests, exact token accounting, queue/TTFT/prefill/decode/service metrics, preemption and scheduler counters, continuous GPU memory/utilization/power telemetry, and an atomic raw bundle plus typed terminal.

- If c64 is structurally valid and improves service time by at least 5% versus c32, run c96 only when memory telemetry is safe and at least eight provider minutes remain.
- If c64 has a typed capacity/OOM failure, run c48 once on the same bench when at least eight provider minutes remain.
- If c64 is valid but improves by less than 2%, is slower, or crosses the economic ceiling, stop without c96.
- Repair ordinary runner, API, telemetry, and retrieval defects in place on the claimed bench. Release the bench with an updated resident-state description; never tear it down.

No MTP, alternate runtime, W4, BF16-KV control, quality inference, prefix change, lower-concurrency repeat, checkpoint transfer, image change, or fresh provider allocation is in scope.

## Resources and limits

- Researcher profile: `execution`.
- Offline preparation: 30 wall minutes, 1 local CPU-hour, 1 GiB.
- Claimed-bench experiment: 20 provider minutes, 0.3334 H200-hours, `$0.85` maximum at the registered `$2.46/hour` experimental rate.
- Storage: no new provider disk; at most 2 GiB of new local/remote artifacts on the resident bench.
- The bench's absolute director watchdog is authoritative and may shorten the arm.

## Portfolio-changing result

Promote c64 or c96 as the new text-only default non-reasoning economic operating point only if the paired-quality gate has passed, all requests and token accounting are valid, and measured service time improves by at least 5% over c32 while remaining below the campaign ceiling. A valid sub-2% gain, regression, capacity failure with no viable c48, or inability to obtain a compatible released bench closes this concurrency line without changing the c32 pass.
