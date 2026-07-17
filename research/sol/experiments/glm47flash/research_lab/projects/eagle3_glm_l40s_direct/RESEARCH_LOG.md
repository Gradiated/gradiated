# Research log

## 2026-07-16 — Director opening handoff

- Decision: Admit the exact-model EAGLE3 candidate as the sole paid lane after n-gram cleanup, but require zero-cost memory, one-patch runtime, and scheduler viability before create.
- Evidence: The 32k-to-target mapping is proven exact; pinned vLLM already implements it and blocks only at the target-type admission observed so far. The model card's H200 acceptance/speed is a prior, not L40S evidence.
- Absolute decision: one target-verified cache-off 8K/1K c16 endpoint must complete within 300 seconds at `>=594.466` output tok/s. No adjacent control or parameter sweep.
- Guardrail: `$1.00`, 3,900 seconds, one create, proven launcher/owner/watchdog, methodology off, terminal archive/spend/zero-cleanup. Close at `$0` if memory, scheduler, or more-than-one-patch admission fails.

## 2026-07-16 — zero-cost runtime close

Question: can the pinned EAGLE3 draft execute target-verified proposals for the fixed 8,192-input / 1,024-output c16 arm? Action: materialized the exact public revision under `artifacts/draft-c43b5f18f59b8fba69e8c0d585fb0e614cf42af1`; all three files and the safetensors tensor header are content-addressed in `CONTENT_ADDRESS.json` (whole draft SHA-256 `ea0f7a60a8efd7bb2c42d4db2e2b6995bc1cac800abee9a7eb14e352ee4fda46`, 290,884,320 bytes, 15 tensors). The draft config is exact but declares `max_position_embeddings=4096`. Pinned vLLM `SpeculativeConfig._maybe_override_draft_max_model_len` admits no value larger than the draft maximum and otherwise selects the minimum draft/target maximum, thus resolves this draft to 4,096 tokens.

Evidence/interpretation: every mandated request starts at 8,192 tokens, beyond the draft context before decoding. The only proposed `glm4_moe_lite` allowlist addition therefore cannot produce an exact EAGLE3 proposal/verification path; a target-only fallback would have zero proposal and accepted tokens and stays below the `594.466` tok/s gate given the `552.1710554232396` contextual stock rate. The pinned runtime otherwise allows EAGLE methods to retain asynchronous scheduling, so this is distinct from the n-gram scheduler collapse. `PREFLIGHT_CLOSE_2026-07-16.json` records the content, source, scheduler, and decision evidence.

Decision: `RUNTIME_CLOSE` at `$0`; no source patch or provider create. Do not alter the fixed workload or launch a successor in this project.
