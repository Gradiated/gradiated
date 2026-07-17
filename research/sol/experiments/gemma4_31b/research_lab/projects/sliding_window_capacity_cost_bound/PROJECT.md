# Gemma 4 sliding-window capacity and cost bound

## Decision question

Would reducing the exact model's 1,024-token local-attention window create a large enough capacity discontinuity or attention-work reduction to justify one later quality-aware candidate, independently of the active FP8 kernel experiment?

This is an explicitly non-quality-preserving model-change screen. It may nominate one window geometry for later matched performance and quality work, but it cannot establish endpoint speed, quality, or production eligibility.

## Why this matters now

Gemma 4 31B has 50 local-attention layers and 10 global layers. The completed L40S accounting places BF16-KV c8 at 45.046 GiB, 0.342 GiB above the conservative 44.704 GiB envelope, while the primary workload is prompt-heavy at 4,214 input and 358 output tokens. A shorter local window changes KV residency and QK/AV work without changing the 31B weight representation. This is materially different from the live exact-shape BF16/FP8 linear-kernel lane and can be bounded at `$0` while that durable owner retains exclusive provider control.

## Authoritative inputs

- `../../CAMPAIGN.md`
- `../exact_geometry_runtime_opportunities/GEOMETRY.json`
- `../fp8_l40s_fit_economic_falsifier/MEMORY_ACCOUNTING.json`
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`
- `../fp8_kv_c8_retained_arm/FP8_KV_ARM.json`

Use the exact pinned model revision and geometry from these artifacts. Do not query or mutate any provider, inspect or alter the live owner, download checkpoints, or wait for its terminal.

## Immediate experiment

Build a deterministic analytical/simulation packet comparing the 1,024-token control with candidate local windows of 768, 512, and 256 tokens:

1. Recompute exact local/global K/V bytes and total conservative residency for the 4,214/358 primary geometry and 10K single-stream view at c1, c4, c8, and c16, for BF16 KV and the already specified FP8 per-token-head KV representation. Preserve all non-KV accounting from the authoritative packet and expose every allowance rather than silently changing it.
2. Compute exact QK/AV attention FLOPs and compulsory attention-state bytes for prefill and decode under the hybrid five-local/one-global pattern. Separate projection/MLP/vocabulary work, which the window does not save. Report theoretical endpoint upper bounds only; do not turn FLOP or byte ratios into requests/s.
3. Identify whether any candidate crosses the c8 or 10K L40S capacity envelope and whether its maximum possible end-to-end effect can clear the campaign's 5% relevance threshold under conservative prompt/decode denominators. Include sensitivity to useful background batching rather than preserving an interactive latency assumption.
4. Account for semantic risk: reduced context is not execution-equivalent. State which traffic or evaluation slices would be required before a nominated candidate could become credible.

Nominate at most one future candidate, and only if it creates a measured-input capacity discontinuity or retains a conservative theoretical path to at least 5% sustainable-cost improvement. Otherwise close the line. Do not prepare a second retained-session arm for the current live owner; its one conditional FP8-KV follow-up is already preregistered.

## Artifacts and budgets

- Terminal artifacts: `WINDOW_BOUND.json` with formulas, identities, inputs, and sensitivity rows; `DECISION.md` with the nomination or closure.
- Wall clock: 45 minutes.
- Compute: at most 1 local CPU-hour; no CUDA.
- Storage: at most 256 MiB.
- Provider mutation and spend: prohibited; `$0`.

