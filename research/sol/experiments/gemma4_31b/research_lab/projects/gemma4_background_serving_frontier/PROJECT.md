# Gemma 4 background serving-system frontier

## Question

Can model-specific scheduling, batching, cache policy, graph capture, or prefill/decode organization reduce exact Gemma 4 serving cost by at least 5% while preserving the model computation and OpenRouter request/tool behavior?

## Work

Use the exact 4,214/358 prompt-heavy distribution, 12.7% cache-read share, and separate AA 10K single stream. Analyze and directly compare the strongest few interactions among background pooling, c16/c32 occupancy, async scheduling, chunked prefill, CUDA-graph geometry, prefix reuse, and hybrid local/global attention scheduling. Start from measured endpoint telemetry and pinned source; do not run a broad parameter sweep or preserve interactive latency assumptions when background-agent traffic can wait.

Run one bounded actual-server comparison on a compatible retained bench when available; otherwise produce and execute the fastest exact simulation or component falsifier while queued. Preserve complete-request throughput, queueing, memory, failures, power, and all-in cost. Outputs need only cheap validity/coherence checks during exploration. Full GPQA-Diamond and TauBench evaluation is deferred to performance survivors.

## Limits

60 wall minutes, at most 35 retained-GPU minutes and `$1.50`, 4 local CPU-hours, and 3 GiB artifacts. Avoid setup replay and release without teardown.
