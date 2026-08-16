# H100 paged-FP8 packet v2 execution audit

## Question

Is `h100_paged_fp8_actual_consumer_packet_v2` a genuinely start-ready pinned-vLLM H100 program, or does it still only specify/approximate the required native forward context, metadata, cache, selected backend, counters, and matched arms?

Inspect `START_PACKET.json`, `paged_consumer_program.py`, its hashes, and the exact pinned source evidence. Do not query or mutate provider, use GPU/image/checkpoint/compiler, or poll the live W4 owner. Execute only CPU/static checks. Verify every claimed actual call exists on the reachable path with correct signatures and concrete native metadata construction; verify local/global geometry, BF16/E4M3 cache arms, output oracle, timing, counter command/range, sentinel/sweep trigger, aggregation, transitive binding, and typed failures. Return content-addressed `AUDIT.json` with `pass_start_ready`, `pass_with_limits`, or `fail_not_start_ready`; do not repair the packet.

Budgets: 15 wall minutes, 1 local CPU-hour, 256 MiB retained plus 128 MiB temporary, `$0`, no GPU/provider.
