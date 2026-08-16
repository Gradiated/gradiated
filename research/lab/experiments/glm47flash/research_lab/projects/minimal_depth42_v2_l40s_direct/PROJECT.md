# Clean minimal-depth-42 direct L40S measurement

## Question

Does the checksum-closed five-block/42-layer physical proxy load on L40S and clear the campaign's `594.466` output-token/s (`$0.514/M` at `$1.10/hour`) gate at c16 or c32 on the exact 8,192-input/1,024-output background workload?

## Why this matters

The full 47-layer current-AWQ model is valid at c16 (`552.171055` tok/s) but analytically exceeds the c32 memory envelope. The 42-layer proxy is the smallest materialized model divergence with robust projected c32 capacity: removing source blocks `[6,15,24,33,42]` projects `43,666.023 MiB`, leaving `2,401.977 MiB` against the measured `46,068-MiB` envelope. Its conservative c16 transfer point is only `597.529` tok/s and the robust uncertainty interval crosses below the gate, so no further offline bound can decide it. The first root failed only a self-referential metadata checksum; the clean v2 root now passes every payload checksum and preserves all model tensor bytes. A direct c16/c32 endpoint is the campaign's nearest-original remaining performance experiment.

## Fixed inputs and evidence

- Candidate root: `/root/.cache/glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1`.
- Candidate contract SHA-256: `5dbf26dc16a1cabbdb36eb256a996a11cf44c71c702b72686806a68a3bb1a290`.
- Runtime manifest SHA-256: `cfee71f350b69a931bc6700712db9850780c30f2e8aa51a406ce9ac7a668cdda`; checksum-list SHA-256: `87d080fa3b10a184abf39e050f6dd67264b32394b43d45caecd93d32e3512950`.
- Four immutable shards total `16,658,558,680` file bytes and contain `16,654,390,736` indexed tensor bytes; all 12 served-payload rows pass `sha256sum -c`, layers are exactly `0..41`, and no MTP/layer-47 payload is present.
- Source/identity evidence: `../minimal_depth42_clean_materialization/`, `../minimal_depth42_exact_loader_falsifier/`, `../student42_measured_depth_transfer_falsifier/`, and `../minimal_change_c32_codesign/`. The frozen failed root `/root/.cache/glm47flash-awq-minimal-depth-4c84badbce22` is prohibited.
- Source checkpoint/tokenizer: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`; preserve tokenizer/config/template identities and reasoning-off generation.
- Runtime: pinned vLLM `0.15.0` plus Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`.
- Proven launcher: `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, direct external systemd owner/watchdog, current L40S-AWQ path, methodology off.
- Workload/economics: cache off, `num_kv_splits=4`, 8,192 input/1,024 output, background arm envelope 300 seconds, planning `$1.10/hour`, absolute gate `594.466` output tok/s. Quality is deferred but mandatory.

## Execution contract

This project is the sole provider-mutation owner with at most `$1.00` and 3,900 seconds. In the same researcher turn, first make one narrow shared-validator admission for the exact clean-v2 root and hashes above. Preserve stock and student39 behavior; explicitly reject the frozen failed root, wrong student, arbitrary manifest bytes, symlinks, and one-field drift. Record post-edit launcher/remote-validator hashes and pass focused tests plus the execution-equivalent no-mutation terminal. Do not rebuild, rewrite, re-manifest, or alias the candidate. A local failure closes at `$0`; a validator patch or readiness artifact alone is not terminal.

If local admission passes, launch immediately with the proven direct controller using `--profile l40s-awq`, `--scientific-mode awq`, `--num-kv-splits 4`, `--max-num-seqs 32`, `--frontier-concurrencies 16,32`, `--background-arm-envelope-seconds 300`, and `--absolute-timeout-seconds 3900`. Run one server and two complete batches at c16 and c32, prefix caching off. c32 is primary; a valid c32 OOM or miss does not erase a completed c16 result. Return after one grouped durable-owner snapshot; later reconciliation owns the terminal.

Retain exact loader/key-consumption and compressed-tensors dispatch evidence, peak/steady VRAM, all request rows, throughput, completion/TTFT/TPOT, cache deltas, GPU utilization/power/clocks, semantic diagnostics, complete output-token histograms, useful GPU seconds, provider exposure/spend, authenticated archive, and zero final instance/disk inventory. Methodology remains off.

Return exactly one terminal result:

- `ECONOMIC_PASS`: at least one complete arm finishes within 300 seconds at `>=594.466` output tok/s; report c16 and primary c32 separately;
- `SCIENTIFIC_FAIL`: valid complete arms miss the absolute gate;
- `LOAD_CLOSE` or `MEMORY_CLOSE`: exact candidate load/dispatch or required workload residence fails;
- or one typed provider/operational terminal before science, without model inference.

No stock arm, c24, training, recovery, broad quality, EAGLE/ngram/MTP, FP8 KV, second checkpoint, runtime upgrade, retained instance, retry, second create, project-specific controller, or successor preparation. One material in-place correction after create is allowed only within the existing owner and deadline.

## Available resources

Use the fixed projects and clean root above, the proven campaign launcher/provider tools, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
