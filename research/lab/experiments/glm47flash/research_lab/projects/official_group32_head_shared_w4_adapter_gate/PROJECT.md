# Official group-32 head/shared W4 adapter gate

## Decision question

Can one narrow pinned-runtime adapter consume **official** compressed-tensors `uint4b8` group-32 weights for the exact `ParallelLMHead` and 46 serving shared experts, without BF16 duplicates or fallback, so the full-47 c16/c32 endpoint is finally runnable?

This is the last bounded implementation attempt for the campaign's first-priority selective-W4 intervention. The quarantined roots in `../full47_head_shared_w4_c32/` used two's-complement nibbles and an oracle patched after import; they are negative implementation evidence, not W4 science. Do not reuse or repair those roots. The group-128 project tested a different, more lossy representation and remains closed.

## Fixed opportunity and scope

- Immutable source checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Exact serving scope: `lm_head.weight` plus gate/up/down weights for shared experts in layers 1–46: 139 BF16 tensors, with layer 47 MTP, layer 0, embeddings, routed experts, routing/top-k, MLA/KV, and depth unchanged.
- Official group-32 payload saves `1,029.966629 MiB`, projecting c32 from `46,875.7` to `45,845.733 MiB`: only `222.267 MiB` below the `46,068-MiB` visible envelope and `1,313.733 MiB` above the `44,532-MiB` robust convention. This can nominate nominal-fit endpoint science, never a robust memory claim.
- Pinned serving identity: vLLM `0.15.0` derived runtime and its compressed-tensors WNA16/Marlin path on SM89.

## Immediate `$0` gate

Within 1,200 seconds, make one project-local, minimal adapter and exercise it in a **fresh pinned process**. Do not materialize a full checkpoint, use a GPU/provider, install another runtime, edit a shared launcher, or spend.

1. Produce representative head and shared-expert packed/scale/shape tensors only through the pinned official compressed-tensors producer using symmetric group-32 `uint4b8`. Compare candidate bytes with official pack/unpack; no custom nibble encoder or self-authored roundtrip can establish readiness.
2. Limit the runtime change to selecting the existing W4 linear method for the exact `ParallelLMHead` while leaving embeddings BF16. Shared experts must continue through the native `Linear` path. A broad matcher/loader rewrite closes.
3. In a fresh process instantiate the actual `ParallelLMHead` and an exact shared-expert module, then exercise real parameter registration, load, post-load/repack processing, and the actual consumer path available in the pinned environment. Prove exact WNA16 method selection, expected keys, no missing/unexpected keys, no resident BF16 duplicate/fallback, and no unrelated module match. A post-import source edit or fixture that never invokes the patched path closes.
4. Preserve vocabulary partitioning, logits shape/dtype/device, bias and sampler contracts, and exact separate-versus-shared-sum semantics. Record finite reconstruction error and saturation for real head plus gate/up/down samples; use the checkpoint's declared calibration/observer behavior where applicable rather than substituting absmax.
5. Account for actual packed, scale, shape, mandatory repack, and duplicate bytes. Fail if runtime overhead consumes the `222.267-MiB` visible margin.

Return `OFFICIAL_SELECTIVE_W4_RUNTIME_READY` only if the official producer and actual pinned consumer pass. If target execution cannot occur without CUDA, return the precise import/compile/dispatch boundary; do not promote source presence. Any representation, load, numerical, semantic, or memory failure returns a typed terminal close. A pass directly nominates one later sole-owner full47 c16/c32 endpoint against `594.466/606.355 tok/s`; do not add another readiness ladder.

For that later paid endpoint, prepare the official shared-W4/BF16-head c16 ablation before launch. Retain the verified runtime only if valid combined c32 lands in `[594.466,606.355)` and the content-bound ablation is ready within ten minutes through the existing retained-session path and the same sequential owner/watchdog; otherwise clean immediately.

## Starting evidence

- `../full47_head_shared_w4_c32/` (quarantined implementation and exact serving scope)
- `../full47_group128_w4_codesign_gate/` (official packer and native-dispatch negative; do not transfer its MTP-contaminated memory total)
- `../lm_head_w4_bridge/`
- `../residual_w4_completion/`
- `../../hardware/L40S.md`

