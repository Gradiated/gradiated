# Gemma 4 H200 local-KV-head discriminator

## Question

Does changing the 50 sliding-attention layers from 16 to 8 KV heads, while retaining 32 query heads, head dimension 256, all 60 layers, MLP width, residual width, and global-attention geometry, reduce the exact H200 fused-QKV plus paged-KV boundary by at least 5% of the measured `0.3633031778124973` seconds/request endpoint?

This is a checkpoint-free hardware discriminator for one small architecture change. It is not evidence that an untrained 16→8 checkpoint is usable. Exact sampled weights already falsify a no-training adjacent-head merge, so checkpoint conversion and quality work remain forbidden unless the measured mechanism passes.

## Why it matters

The completed co-design proxy nominates this as the only model/chip change with both material work relevance and an established recovery method. Across the 50 local layers, 16→8 KV heads changes the c32 fused-QKV shape from `[32,5376,16384]` to `[32,5376,12288]`, removes `150,156,083,200` compulsory decode KV bytes/request, and has a measured-anchored relevance estimate of 10.98%. The physical risk is decisive: the assumed H200 QKV grid falls from 128 blocks to 96, so underfilled-SM and fixed-launch costs may erase the nominal savings. A direct exact-shape measurement is cheaper and more informative than training first.

## Bound identities and evidence

- Model identity: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime image: `docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`, pinned SGLang v0.5.12 source lineage.
- Co-design result: `../gemma4_small_architecture_chip_codesign/artifacts/exact-shape-proxy-20260718T1538Z/RESULT.json`, SHA-256 `b85d11488e4ba85a4b472e70b818985bd4c660802ca9e8f575c845367a694d0b`.
- Co-design status/nomination: `../gemma4_small_architecture_chip_codesign/STATUS.json`, SHA-256 `bc7a6f58319c17751eadb46440b2063f708cb755763f766bb65b1efee6627861`.
- Exact-mix canonical reference: `../gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, used only to report transfer relevance; the preregistered discriminator gate remains 5% of the measured `0.3633031778124973`-second endpoint that anchors the co-design proxy.

Mechanically re-hash these files before the first paid invocation. Snapshot any shared source or benchmark bytes under this project before claiming the bench.

## Direct experiment

Use the director-allocated shared H200 and one retained mutable development claim. Inspect the pinned fused-QKV and selected page-1 FP8-E5M2 paged-attention paths, then implement the smallest exact-shape benchmark that compares baseline 16-head local KV against candidate 8-head local KV without dense repeated-KV materialization or fallback.

Measure paired, randomized baseline/candidate rows for:

- fused-QKV `[32,5376,16384]` versus `[32,5376,12288]`;
- matched local paged-KV write/read and attention at 1,024-token window, 32 query heads, head dimension 256, page size 1, and the campaign's 4,214-prompt/358-output decode geometry;
- enough repetitions and cold/warm controls to resolve launch, HBM/L2, and active-SM-wave effects.

Consume every output and require finite nontrivial results. Record CUDA-event and synchronized-wall timing, selected source/operator identities, allocation deltas, achieved bandwidth, active blocks/SM waves, launch count, and the smallest available DRAM/L2/warp counters. Missing optional counters may limit interpretation but does not erase valid timings.

The component passes only when the conservative 50-layer aggregate saves at least `0.0181651588906249` seconds/request, with no fallback, illegal access, dense/repeated KV allocation, or numerical failure. Report the implied fraction of the later `0.9194573941250042`-second exact-mix endpoint as a derived transfer bound, not an endpoint claim.

On pass, stop after preserving the discriminator terminal and release the bench ready. The next director turn may retain the same bench and extend this same project into bounded GQA checkpoint conversion and cheap retrieval/coherence gates. On miss, close the 16→8 local-head line without training, endpoint staging, or a more aggressive head-count sweep.

## Limits

- Researcher profile: `deep` for source/geometry/accelerator causal reasoning.
- Wall clock: 120 minutes, ending by `2026-07-19T14:17:22Z`.
- Shared H200 claim: at most 70 minutes; one scientific candidate program with in-place repair of ordinary pre-invocation build/API/path defects.
- Provider exposure authority: `$6.00` including the director-created preemptible H200 and disk; absolute cleanup watchdog `2026-07-19T14:47:22Z`.
- Storage: one 100-GiB provider disk; 5 GiB retained project artifacts plus 3 GiB temporary.
- No checkpoint transfer, model load, training, distillation, endpoint run, broad quality evaluation, second architecture candidate, tile/split sweep, second allocation, or researcher-owned provider lifecycle mutation.

Retrieve a typed terminal, exact program/source hashes, paired raw rows, numerical/allocation oracles, and telemetry. Release without teardown for director disposition.

## Director extension — bounded GQA conversion and conditional endpoint

The checkpoint-free discriminator passed with `0.03213170265625002` seconds/request of conservative saving, 1.77× the preregistered gate. Extend this same scientific project; do not create a conversion, repair, readiness, or quality successor.

Stage the exact eight-file, `62,578,655,208`-byte checkpoint from the local path content-bound in `../gemma4_h200_attention_endpoint_integration/IDENTITIES.json` (SHA-256 `79958515caad9b6e30db161a137a24291be31fb28b68ad982652261913f89516`). Bind the passing discriminator terminal (`1a3e4d5d1693d4673a99dd94a20fc777a1c2477418c57da52fab8a8e9d89f99b`) and result (`33895eee6e8af43f97719a3dda3f86b799377f5c1e0ed20204a29ca40d273a76`) before mutation.

Implement the exact 16→8 local-KV-head representation in the pinned SGLang consumer while leaving all global layers, query heads, head dimensions, MLPs, residual width, tokenizer, template, and non-local-KV checkpoint tensors unchanged. Initialize each new local K/V head by the preregistered adjacent-pair mean, then run one bounded teacher/student schedule over only the local K/V projection tensors. The schedule must add an end-to-end teacher target (logits or final hidden state) to held-out local-attention/block fidelity so it does not repeat the prior head-dimension project's block-only failure. Freeze the schedule, optimizer, request split, and trainable tensor manifest before the first update; no second schedule, head-count alternative, optimizer sweep, or loss-weight sweep is allowed.

Use the immutable 24/8 split of the 32 canonical request bodies where practical, with bounded token sampling or streaming capture to fit the resident bench. Require the pair-mean baseline and trained candidate on the same eight held-out requests. The candidate must improve aggregate held-out normalized RMSE and cosine over initialization, avoid a material end-to-end teacher-target regression, and preserve checkpoint metadata outside the declared local K/V overlay.

Only after those fidelity gates pass, load the patched exact consumer and require:

- 3/3 finite, nonempty, nonrepetitive coherence prompts;
- a small deterministic 10K-context retrieval set with all exact answers recovered;
- no fallback, dense/repeated KV materialization, illegal access, or model/runtime identity drift.

Only after all cheap quality gates pass, invoke the frozen canonical c32 exact-mix runner once: 32/32 finite nonempty responses, exactly 4,214 prompt and 358 completion tokens each, 17,120 cached and 117,728 fresh prompt tokens, idle preflight, and HTTP-200 cache flush. Retain any valid improvement below `0.9194573941250042` seconds/request; promote to broad GPQA-Diamond and TauBench only at or below `0.8734845244187539`. A fidelity, coherence, retrieval, integration, or performance miss closes this conversion schedule without another training run.

Extended aggregate limits: `$18.00` reserved, at most 220 H200 claimed minutes, 270 wall minutes ending by `2026-07-19T16:45:00Z`, 20 GiB retained plus 12 GiB temporary artifacts beyond the staged checkpoint/image, and absolute director watchdog `2026-07-19T17:15:00Z`. Keep the same bench, image, caches, and one mutable owner across checkpoint transfer, integration, training, cheap gates, and any conditional endpoint. Release ready; researchers do not tear down provider resources.

## Director amendment — preserve the producer and repair only the consumer

The sole producer invocation is complete and admitted. `DISTILL_TERMINAL.json` records 24 optimizer updates, a passing fidelity gate, improvement over pair-mean initialization in both held-out block fidelity and final-hidden fidelity, and a content-addressed 100-tensor overlay of `2,202,022,184` bytes with SHA-256 `e29faa6768d22aa6cae56bb15253d02f6af0aca2abdd6d4f0092a436cea05780`. Preserve that overlay and its terminal. No further training, distillation, conversion, calibration, checkpoint transfer, capture, schedule change, or scientific producer invocation is authorized.

`OWNER_TERMINAL.json` is an ordinary consumer startup failure, not a conversion result: the pinned SGLang `model_config.py` guard rejects the already-transformed mixed geometry `{num_key_value_heads: 4, swa_num_key_value_heads: 8}` because it still requires local KV heads `16` before assigning `8`. The first owner released after its controller-bound overlay copy timed out at 900 seconds and `585,953,280` partial bytes. The full content-addressed overlay remains durable on the protected H200 beside the exact checkpoint, pinned image, and caches; compact terminal, hash, fidelity, and traceback evidence is already local. Reclaim that same bench immediately and use the remote overlay in place. Patch only this mixed-geometry consumer binding, prove that the runtime binds global KV `4` and local KV `8` without fallback or repeated-KV materialization, and resume at server startup. Then run the existing 3/3 coherence, deterministic 10K retrieval, and conditional exact-c32 sequence unchanged. Do not put another bulk retrieval on the GPU critical path; retrieve the full overlay only after the final terminal, or concurrently only if it cannot delay the consumer. A genuine incompatibility or a downstream gate miss is terminal; the consumer repair may not recreate the producer.

## Director closure — coherence-negative conversion

The consumer-only repair bound the intended global-KV4/local-KV8 geometry, loaded the remote content-addressed overlay, and reached the exact served coherence consumer. All three preregistered prompts failed with finite but repetitive gibberish, including the exact-token, arithmetic, and structured-output rules. This is the quality terminal specified above. Do not run deterministic retrieval, c32, a second producer, a different schedule, a partial-layer/head-count alternative, or another consumer repair.

Before director cleanup, preserve the already-created producer artifact by resuming the existing `585,953,280`-byte local partial copy to exactly `2,202,022,184` bytes and verifying SHA-256 `e29faa6768d22aa6cae56bb15253d02f6af0aca2abdd6d4f0092a436cea05780`. This final read-only retrieval must not claim the GPU or alter the remote checkpoint, overlay, image, caches, server, provider, or inventory. Once the verified local overlay and a compact retrieval terminal are durable, mark the project terminal for director teardown.
