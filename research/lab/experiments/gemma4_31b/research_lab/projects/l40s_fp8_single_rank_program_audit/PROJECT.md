# L40S FP8 single-rank live-program audit

Independently audit the immutable live bytes of `../l40s_fp8_single_rank_context_falsifier` after create. Verify real single-rank NCCL/CUDA TP=PP=DP=1 init/destroy order and identity, sentinel atomicity/fail-close, actual FP8/BF16/head/KV/W4 consumers, exact shapes and c12 aggregation, positive/stable timing and oracle gates, telemetry acceptance, residual maxima, strict W4 trigger/same-owner/deadline behavior, transitive byte capture, remote hash equality, durable owner/watchdog, accounting/retrieval/cleanup. Inspect behavior and exact lines/hashes, not substrings.

This is `$0` read-only advisory work. Do not edit the paid project, signal/stop/restart/poll its service beyond local artifacts, query/mutate provider, invoke GPU, or authorize spend. Write `AUDIT.json`, concise log/status, and return `pass_advisory`, `fail_quarantine_science`, or `insufficient_immutable_evidence`.

Budgets: 15 wall minutes, 1 local CPU-hour, 128 MiB retained + 64 MiB temporary, `$0`, no provider/GPU.
