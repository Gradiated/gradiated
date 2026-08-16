# Full-47 MoE-width-1024 direct L40S measurement

## Question

Can the full 47-layer serving graph retain 64 routed experts, top-4 routing, its shared expert, MLA rank 512, and symmetric group-32 W4 while reducing only the 46 serving MoE intermediate widths from 1,536 to 1,024, and thereby deliver a complete c32 endpoint at or above `606.355` output tok/s on L40S?

## Why this matters

The earlier width screen used the old `535.286` c16 denominator, targeted 32-GB placement, and counted layer 47 even though it is the separate MTP payload. Correcting to serving layers 1–46, width 1,024 removes about `5,244 MiB` of routed-plus-shared expert payload and projects the full-model c32 peak from `46,875.7` to about `41,631.7 MiB`, roughly `2,900 MiB` inside the `44,532-MiB` robust limit. It preserves every layer, expert identity, routing decision count, attention/KV dimension, and the already-supported W4 representation, making it a smaller practical divergence than depth deletion or expert-count reduction.

The new evidence makes the performance question narrow but unresolved. Applying the closest measured c32/c16 packing ratio to the valid full-model r3 c16 result gives `585.046` tok/s before width credit. The lower explicitly attributed routed-plus-shared expert interval and a one-third width reduction produce only an optimistic `609.9–611.0` tok/s proxy. That small margin is not nomination evidence; a direct target-GPU endpoint is the fastest credible falsifier, and smaller-N grouped-GEMM realization may erase it.

## Fixed evidence and identity

- Source checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, config SHA-256 `079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9`, index SHA-256 `b9c53433e94f2fe7870cdbc3fcb6ed1431eb500c5242a039de93fef4bb988695`.
- Serving graph: dense layer 0 plus MoE layers 1–46. Layer 47 is MTP payload and must not be counted or served. Preserve 64 routed experts, top-4, one shared expert, group-32 W4 routed tensors, BF16 shared tensors, MLA/KV, scheduler, tokenizer, and templates.
- Prior exact width shapes: `../expert_width_32gb_architecture/`. At width 1,024, routed gate/up packed tensors are `[1024,256]`, down tensors `[2048,128]`, and scales `[1024,64]`/`[2048,32]`; the 128-wide tile gate passes.
- Current endpoint evidence: `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json` at `552.171055` c16; `../minimal_depth43_v2_l40s_direct/` supplies the closest measured c32/c16 ratio `1.059538`. These are bounds and context, not matched throughput transfer.
- Proven runtime/lifecycle: pinned vLLM `0.15.0`, Transformers `1618d44b9295361607ec74d7be860ba886aac039`, `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, and the retained recovery path `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_recover_existing.py`.
- Workload/economics: cache off, 8,192 input/1,024 output, `num_kv_splits=4`, c16/c32, 300-second background envelope, planning L40S `$1.10/hour`, absolute `594.466` and robust `606.355` tok/s gates. The price inventory is fresh and provider inventory is zero at handoff.

## Execution contract

This project is the sole provider-mutation and spend owner, with one create, one sequential external-systemd owner plus cleanup watchdog, at most `$1.25` and 4,500 allocation seconds. Before create, derive a project-local deterministic streaming materializer and content-address both width-1,024 and conditional width-768 roots outside the repository. Slice only serving-layer routed W4 codes/scales/shape metadata and BF16 shared-expert gate/up/down tensors, set the exact width config field, preserve every other byte, and omit MTP from the served identity. Record tensor/index closure, shard hashes, idempotent reuse, no symlinks, exact saved bytes, and pinned constructor/loader plus ordinary-Marlin and fused-MoE dispatch. If either candidate needed for the declared retention branch is not identity-closed before create, disable retention and run only width 1,024.

Fail at `$0` on a representation, loader, dispatch, manifest, or robust-memory violation. Otherwise use the proven shared launcher—no project-specific controller—for one width-1,024 server and complete c16 and c32 batches. Retain request rows and token histograms, finite/no-NaN diagnostics, exact output counts, throughput/TTFT/TPOT, peak and steady VRAM, GPU utilization/power, runtime and kernel identities, setup versus useful GPU seconds, provider exposure, authenticated archive, and cleanup evidence. This is architecture-cost evidence; development quality may be recorded but does not certify the model.

Because the measured depth43 setup/staging time (`838.036 s`) materially exceeded scored GPU time (`157.517 s`), preregister exactly one adjacent follow-up. Retain the allocation only if width 1,024 loads, completes the authoritative c32 workload with valid diagnostics, and returns `>=592.9` but `<606.355` tok/s. Then, within the same absolute deadline and under the same sequential owner/watchdog, use `--reuse-staged-runtime` only, freshly restage and verify the content-addressed width-768 checkpoint, and run c32 once. Do not reuse checkpoint bytes or mutable model state. If width 1,024 reaches `606.355`, falls below `592.9`, fails science, or the width-768 root is not ready within ten minutes, tear down immediately. Never retain for planning or artifact retrieval alone.

Return one terminal family decision:

- `NOMINATE_WIDTH1024` if width 1,024 completes c32 at `>=606.355` tok/s inside the robust memory and 300-second gates;
- `NOMINATE_WIDTH768` only if the named retention trigger fires and width 768 then clears the same gates;
- otherwise `WIDTH_FAMILY_CLOSE`, with the exact representation, load, memory, endpoint, operational, or identifiability boundary.

No stock control, depth change, expert-count/top-k change, shared-expert removal, MLA/KV change, precision change, runtime upgrade, custom kernel, training, recovery, broad quality campaign, second create, untriggered retention, or successor controller. One material pre-create correction is allowed; a readiness artifact is not terminal.

## Available resources

Use the fixed projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
