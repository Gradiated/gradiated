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
