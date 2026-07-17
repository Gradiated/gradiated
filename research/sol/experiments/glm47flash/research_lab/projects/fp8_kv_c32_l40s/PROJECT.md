# FP8-KV c32 L40S placement experiment

## Question

Can Ada-native FP8 KV state make the exact current-AWQ c32 background workload fit on one L40S and improve sustainable output-token cost by at least 10% over the measured BF16-KV c16 control?

## Why it matters

The measured current-AWQ c16 point is 535.286 output tok/s at 98.36% mean GPU utilization and peaks at 44,103 of 46,068 MiB. Ordinary BF16-KV c32 was closed because it exceeds the memory envelope. The exact MLA state is 1,152 bytes per token per serving layer: for 47 layers and the fixed 8,192-input/1,024-output geometry, BF16 KV is 7.436 GiB at c16 and 14.871 GiB at c32. FP8 halves those bands, so c32 FP8-KV has approximately the same raw KV bytes as the admitted c16 BF16-KV point. This is a real representation/capacity discontinuity, not another unchanged-concurrency extrapolation. L40S SM89 supports FP8, and the campaign permits a semantics-changing cost proxy before later quality certification.

At the fresh `$1.10/L40S-hour` planning rate, the campaign's `$0.514/M` discovery target requires 594.466 output tok/s, or 1.11056x the 535.286 c16 control. The actual Nebius experiment rate remains `$0.8581222/hour` plus the already included disk basis; use it only for experiment spend.

## Experiment

Use the same content-addressed inputs and runtime as the successful current c16 result:

- launcher: `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, using its explicit `l40s-awq` profile and the successful launcher's create reconciliation, watchdog, transfer, retrieval, and cleanup path;
- current AWQ checkpoint and tokenizer: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, four weight shards, existing manifest;
- runtime: digest-pinned vLLM 0.15.0 image and current content-bound Transformers derivation already named by the launcher;
- workload: cache off, 8,192 input / 1,024 output, `num_kv_splits=4`, exact fixed requests, 300-second background completion envelope.

Run one retained L40S allocation with these scientific arms, in order:

1. Adjacent stock BF16-KV c16 control.
2. FP8 E4M3 KV c16, separating the precision effect from concurrency.
3. FP8 E4M3 KV c32 if and only if the exact load/memory gate passes.

The current shared launcher does not yet expose KV dtype or c32. Those narrow launcher/runner edits are explicitly in scope and must flow directly into this same return's measurement; a patch, source-support check, compile result, or no-mutation artifact alone is not terminal. Reuse the allocation across server restarts. Do not create a project-specific provider controller, change weights, enable prefix caching, tune unrelated kernels, repair MTP/MoE, or add other batch points. Make at most one safe material correction after a pre-GPU failure, then return the typed blocker or scientific result.

Record exact server commands and resolved KV dtype/scales, load success, per-arm peak and steady VRAM, request rows, throughput, TTFT/TPOT/completion envelope, GPU utilization/power/clocks, server metrics, errors/fallback, and compact semantic/quality diagnostics. FP8 output identity is not assumed; quality remains provisional and must be labeled. Retain raw artifacts, content hashes, provider exposure/useful-GPU seconds, and verified zero final instance/disk inventory.

## Budget and stop rule

Maximum provider exposure is 3,900 seconds and `$1.00`, including cleanup. The project is sole provider-mutation owner. A valid FP8 c32 arm must reach at least 594.466 output tok/s with all requests complete inside 300 seconds to survive the cost gate. A load failure, c32 OOM, fallback to BF16 KV, or sub-gate endpoint closes this route. A passing cost proxy nominates later recovery/quality work; it is not yet a deployable or provider-beating claim.

## Portfolio-changing result

Promote FP8 KV only if the retrieved artifacts prove the intended representation and the c32 endpoint clears the 10% planning-cost gate. Otherwise retain BF16-KV c16 and redirect the measured lane away from KV precision and higher concurrency.

## Director readmission — Cycle 41

The r1 allocation produced no scientific evidence. The main launcher was still performing its derived-image bootstrap when a recovery arm concurrently tried to use the local-only image tag; the recovery failed, the overlapping bootstrap paths were interrupted, and cleanup eventually passed. This is a controller-ordering failure, not an FP8 load, capacity, or throughput result.

Authorize exactly one materially corrected r2. Run the existing shared launcher and existing recovery entrypoint sequentially inside one durable systemd-owned command envelope; do not add another controller or modify the current 31-test FP8/c32 contract. The main launcher must first create the instance, build and inspect `glm-vllm:0.15.0-transformers-1618d44`, transfer/verify the checkpoint, run the adjacent stock BF16-KV c16 arm, and retain the allocation. Only after that command reaches its typed terminal may the same durable unit run FP8-KV c16 and then FP8-KV c32 recoveries. Do not launch a concurrent probe, recovery, bootstrap, or repair window.

Use a fresh r2 artifact root and retain service identity, journal, arm boundaries, exposure, and cleanup. If the durable unit cannot be admitted locally, if the serialized main bootstrap fails again, or if any arm cannot start within the single 3,900-second / `$1.00` envelope, close the route without another retry. A readiness artifact is not terminal; the return must contain scientific arms or the typed r2 failure plus verified zero inventory.
