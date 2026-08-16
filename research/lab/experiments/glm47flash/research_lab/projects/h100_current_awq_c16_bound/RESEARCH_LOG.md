# Research log — H100 current-AWQ c16 economic bound

## 2026-07-15 — Director delegation

Opened as an independent zero-provider hardware-transfer screen. The authoritative `$2.80/H100-hour` planning rate requires 1,513.186 output tok/s at `$0.514/M`, or `2.8269x` the measured 535.286-tok/s L40S control; the `$2.50–$3.10/hour` range requires 1,351.059–1,675.313 tok/s. No provider mutation or paid allocation is authorized. The first researcher should bind exact SM90 compressed-tensors/Marlin support and derive a conservative exact-workload bound before proposing any GPU arm.

## 2026-07-15 — Static SM90 admission passes; conservative transfer screen closes at $0

**Question.** Is a matched same-identity H100 c16 measurement justified by a conservative economic bound?

**Action.** Cloned the pinned vLLM `v0.15.0` tag at `f176443…` and ran the new source-bound fixture against the exact checkpoint config. It passed: packed symmetric W4/group-32 is legal Marlin input at SM90 and vLLM's MoE selector prefers `CompressedTensorsWNA16MarlinMoEMethod`; hidden 2,048 and MoE width 1,536 meet the 128-tile and group-32 divisibility requirements. I then combined the measured 535.286 tok/s c16 L40S control with the retained cache-off 8k observer trace. Dense GEMM plus MLA are 67.42% of summed kernel duration; the remaining 32.58% is routing/copy/norm/unclassified work across a 76,964-kernel tail.

**Evidence.** [h100_current_awq_c16_bound.json](h100_current_awq_c16_bound.json) records source hashes, input hashes, hardware/price inventory identities, and calculations. Giving dense/MLA the full H100/L40S BF16 peak ratio (2.733×) while holding the tail fixed yields 935.036 tok/s, `$0.8318/M` at `$2.80/hour` (`$0.8734/M` with a 5% lifecycle allowance), below the 1,513.186 tok/s base gate and 1,588.846 lifecycle gate. The 3.877× HBM-only 2,075 tok/s result is an explicitly optimistic roof, not a funding case. Static source admission is not a real H100 image/model-load execution.

**Decision and next move.** Close this hardware-transfer branch with zero provider spend and do not nominate an H100 arm. Reopen only if new exact-shape evidence shows that SM90 accelerates the currently conservative grouped-MLA/non-GEMM tail or W4A16 dispatch enough to falsify the screen; otherwise allocate to a mechanism that removes that tail or changes serving behavior.
