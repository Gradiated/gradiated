# FP8 layer-dataflow fusion on H200

## Question

Can dynamic activation quantization be fused with adjacent Gemma normalization, gated activation, or residual dataflow so the retained H200 stack removes redundant reads, writes, and launches without changing model geometry?

## Why this matters

The exact current-runtime profile assigns `0.323396400 s` to per-token FP8 quantization and `0.214190627 s` to normalization/activation in a 23.0386-second batch window, before counting memory traffic hidden under neighboring kernels. This is unlikely to close 7.42% alone, but it is a clean stackable opportunity and avoids retuning the rejected CUTLASS gate/up tile.

## Scope and immediate experiment

Bind the exact stack and workload from `../gemma4_h200_v0513_fp8_qkv_residual_profile/BINDINGS.json`, including QKV fusion and the retained deferred local-KV change. Map the actual dynamic-FP8 producer calls to their adjacent operations. Choose the highest-relevance fusion using source and trace evidence—such as RMSNorm-to-FP8 for QKV/gate-up, gated-activation-to-FP8 for down projection, or residual-add/norm/quantization dataflow—and implement it as one coherent candidate. Use best judgment; do not perform a generic kernel or flag sweep.

Measure the exact component path with numerical and invocation proof on H200, then run one contemporaneous c32 endpoint control/candidate pair if the implementation is stable. Keep simple positive gains. Repair ordinary integration defects on the retained bench instead of tearing it down or opening successor projects.

Capture bytes/launches removed, component timing, numerical error, endpoint service seconds/request, exact token/cache accounting, output sanity, useful GPU time, and spend. Do not run broad quality tests unless outputs are obviously broken.

## Resources

- Reuse a director-registered H200 bench; no researcher provider lifecycle actions.
- Up to 150 H200 claim minutes and `$9.00` total authorized spend.
- Release the loaded/cached bench ready for the next project.
- Exclude the rejected `64x256x128` gate/up tile and any broad CUTLASS schedule sweep.

## Director continuation — persisted real-consumer arm

The first component invocation is closed as inconclusive, not negative: the custom producer reached CUDA, but the synthetic benchmark created its down-projection `mat_b` row-major and the pinned CUTLASS consumer rejected it before any numerical or timing row persisted. Do not replay that synthetic-weight arm.

Use the retained H200 and resident checkpoint for one materially distinct component contract. Load one exact Gemma down-projection weight through the pinned runtime so its dtype, shape, strides, storage orientation, and per-channel scales match the endpoint consumer. Invoke the candidate producer once for each admitted M=32/M=2048 shape, persist the quantized tensor, scale tensor, metadata, and hashes before GEMM, and make any downstream consumer repair operate only on those persisted outputs. Preserve the existing numerical and timing gates. Promote to the existing one paired c32 endpoint only on `component_positive`; otherwise release with a typed terminal. This continuation may claim at most 120 minutes and `$4.92`, must release by `2026-07-22T17:45:00Z`, and must not transfer the checkpoint or pull the pinned image again.

## Director iteration 3 — RMSNorm-to-FP8 producers

The consumed gated-activation/down-projection candidate remains closed. This iteration tests a different producer chain. The qualified E5M2 profile records 14,640 `per_token_quant_fp8_small_batch_kernel` calls taking `0.3233964 s` in the exact batch. Gemma's 60 layers over 61 observed forward batches invoke four dynamic-FP8 projections per layer; the QKV and gate/up projections account for the 7,320 inputs immediately produced by pre-attention and pre-MLP RMSNorm. Their normalized BF16 intermediates have no non-linear consumer before `fp8_scaled_mm`.

Use `$kernel-research` to source-bind both live RMSNorm variants, residual ownership, FP8 scale convention, graph shapes, and downstream QKV/gate-up consumers. Implement one shared RMSNorm-to-FP8 producer family that preserves the BF16 residual state while emitting the exact E4M3 activation and per-token scale expected by the unchanged CUTLASS consumers. The prediction is 14,640→7,320 standalone quantization calls plus elimination of the normalized BF16 write/read for those two projection families; this is an incremental dataflow gain, not a GEMM schedule or tile experiment.

After the new `$10` reservation is durable, claim `h200-sync-linear-e00vhh6h29fj68x91g`, stop any incompatible mixed-KV server only after the claim, and restore the qualified E5M2 stack from the manifest-verified checkpoint and pinned image. Run one exact real-consumer component pair covering decode `M=32` and observed prefill shapes, with high-precision RMSNorm and unchanged FP8 consumer oracles, complete output consumption, scale/saturation evidence, graph/path proof, and warm timing. Promote immediately to one profiler-off c32 control/candidate pair only if the component is correct and removes the predicted calls with a conservative positive whole-request bound. Keep any valid simple endpoint gain; do not require 5%.

Do not replay the activation/down candidate, alter CUTLASS schedules, fuse o/down projections, change precision, sweep RMSNorm variants, or add a second candidate. At most 100 H200 claim minutes, 150 wall minutes from first claim, `$10` newly authorized spend, and 8 GiB new artifacts; no checkpoint duplication or provider mutation.
