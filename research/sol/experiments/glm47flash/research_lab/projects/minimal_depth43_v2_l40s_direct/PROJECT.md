# Nested minimal-depth-43 direct L40S measurement

## Question

Can a clean 43-layer proxy that restores the latest skipped source block preserve robust c32 L40S residence and the measured depth42 economic pass while reducing structural and development-quality divergence?

## Why this matters

The 42-layer proxy measured `616.602` output tok/s at c16 and `686.910` at c32, but failed the cheap development quality screen. Its measured c32 peak was `43,871 MiB`, leaving `2,197 MiB` on the 46,068-MiB L40S. The existing robust-headroom convention leaves only `661 MiB` for one restored block plus its c32 KV state: this makes 43 layers the smallest plausible robust divergence, while restoring two blocks cannot retain the same safety margin. Restoring source block 42 yields nested skips `[6,15,24,33]` and keeps the final 13 source layers intact, a more output-proximal fidelity choice than the measured proxy.

## Fixed inputs and evidence

- Exact source: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, config SHA-256 `079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9`, index SHA-256 `b9c53433e94f2fe7870cdbc3fcb6ed1431eb500c5242a039de93fef4bb988695`.
- Deterministic geometry: retain source layers `0..46` except `[6,15,24,33]`, renumber to `0..42`, disable MTP, preserve every other tensor/tokenizer/template byte, and use the served-payload/checksum policy proven by `../minimal_depth42_clean_materialization/`.
- Measured parent: `../minimal_depth42_v2_l40s_direct/`, archive SHA-256 `ee0f3f3b3d3abfa2f9610320a5be44934be8493a61f52a0d339e83ca4b3d8541`, c32 peak `43,871 MiB`, c16/c32 `616.602/686.910` tok/s. Parent quality failed; no quality transfer is allowed.
- Runtime and launcher: pinned vLLM `0.15.0`, Transformers `1618d44b9295361607ec74d7be860ba886aac039`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py` under its direct external-systemd owner/watchdog.
- Workload/economics: cache off, `num_kv_splits=4`, 8,192 input/1,024 output, c16 and c32, two complete batches each, 300-second background envelope, planning `$1.10/hour`, absolute gate `594.466`, robustness marker `606.355`. c40+ is closed by `../minimal_depth42_background_frontier_gate/`.

## Execution contract

This project is the sole provider-mutation owner with at most `$1.00`, 3,900 seconds, and one create. Before any provider mutation, derive a project-local clean v2 materializer from the proven byte-preserving writer and materialize exactly one content-addressed 43-layer root. Record the contract, payload manifest, checksum list, all shard hashes, exact tensor/index closure, idempotent reuse, no symlinks, and no MTP/dangling keys. Do not mutate or alias the source or depth42 roots.

Fail closed at `$0` unless exact restored-block payload plus 32-sequence KV/runtime accounting projects c32 at or below `44,532 MiB`, the campaign's 1,536-MiB headroom boundary. Then add one narrow exact-identity admission to the shared validator, preserving stock, student39, and depth42 behavior; pass focused tests, shell syntax, exact payload hashing, and an execution-equivalent no-mutation terminal. A materializer, validator patch, or readiness artifact alone is not terminal.

If local admission passes, launch immediately with the proven direct controller using `--profile l40s-awq`, `--scientific-mode awq`, `--num-kv-splits 4`, `--max-num-seqs 32`, `--frontier-concurrencies 16,32`, `--background-arm-envelope-seconds 300`, and `--absolute-timeout-seconds 3900`. Run one server and two complete batches at c16/c32 with prefix caching off. Retain exact loader/key and compressed-tensors dispatch evidence, peak/steady VRAM, all request rows, complete token histograms, throughput/TTFT/TPOT, telemetry, semantic and frozen development-quality evidence, spend, authenticated archive, and zero final inventory.

Return exactly one terminal result:

- `ECONOMIC_PASS`: at least one complete arm finishes inside 300 seconds at `>=594.466` output tok/s; report c16/c32 and quality separately;
- `SCIENTIFIC_FAIL`: complete arms miss the economic gate;
- `QUALITY_PROXY_CLOSE`: economics pass but the same development screen is strictly worse than depth42, without claiming full quality;
- `LOAD_CLOSE` or `MEMORY_CLOSE`: exact load/dispatch or required workload residence fails;
- or one typed pre-science provider/operational terminal.

No c40, stock/parent control, training, recovery, broad evaluation, speculative decoding, runtime upgrade, second checkpoint, retained instance, retry, second create, project-specific controller, or successor preparation. One material local correction is allowed only before create.

## Available resources

Use the fixed projects and roots above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
