# Research log

## 2026-07-16 — Director opening handoff

Use one exact layer-24 gate/up/down screen to test a two-sided common basis plus expert-specific reduced W4 cores. This is not the closed additive trunk/delta design. Require approximation, activation, tile, active-work, and conservative `1.63x` component-path gates; otherwise close in one `$0` turn. No training, kernel, provider, or successor work.

## 2026-07-16 — Exact factorization closes on approximation

Question: Does the exact layer-24 two-sided shared-basis form `W_e ≈ U C_e Vᵀ` retain the required approximation while reducing routed work?

Action: Ran the bounded deterministic CPU falsifier over all 64 exact layer-24 gate/up/down group-32 W4 experts from checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, dequantized to FP32. Shared input/output bases were fit from summed per-expert covariance at tile ranks 128/256/384/512; 256 seeded held-out Gaussian activations were evaluated per expert. Runtime was 82.943 seconds, with no provider/GPU/shared-code mutation.

Evidence: All four ranks are group-32 and 128-tile legal. At rank 512, the best approximation point, median/worst relative Frobenius errors were gate `0.9240/0.9301`, up `0.9262/0.9309`, and down `0.9227/0.9318`; held-out median relative L2 was `0.9224/0.9264/0.9220`, and worst cosine was `0.3671/0.3603/0.3626`. These miss the required `0.10/0.20`, `0.15`, and `0.98` gates by large margins. The c32 source-bound shared/core FLOP proxy still predicted `2.087x–2.400x` work ratio at rank 512, so geometry and proxy economics are not the limiting falsifier; this is not measured kernel execution.

Decision: `APPROXIMATION_CLOSE`. The shared two-sided basis does not explain the exact expert weights closely enough to justify kernel or training work. No successor, quality, W4 repair, or provider action is authorized.

## 2026-07-16 — Director evidence caveat

The close is robust because dense unquantized reduced cores already miss by an overwhelming margin. Do not promote the artifact's payload, singular-tail, or execution ratios: reduced cores were not quantized to group-32 W4, original W4 bytes are overcounted, eigenvalue ordering/energy is wrong, and FLOP ratios are synthetic work proxies. None of these favorable-accounting defects can reverse the measured approximation failure.
