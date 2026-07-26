## 2026-07-26 — offline causal offset-head discriminator

Question: can one shared Gemma causal head emit offsets 1–16 and support the
locked `0.500119281574996 s/request` target without changing target
verification or KV authority?

Action: bound pinned Gemma/SGLang producer, tied-head consumer, acceptance, and
KV-compaction source locally; implemented the 6.301M-parameter rank-256 causal
head, offset-weighted loss, one-pass request-owned layer-45/54/60 capture,
deterministic trainer/holdout evaluator, exact-shape fixture, immutable
request-disjoint 4096/512 split, and full draft-plus-verify cost model.

Evidence: `EXACT_SHAPE_FIXTURE.json` executes
`[32,16,5376] -> [512,262144]` with BF16 taps/weight and FP32 logits on
PyTorch meta tensors. `artifacts/capture-fixture/CAPTURE_FIXTURE.json`
preserves request ownership through a forced reorder. The H200-bound grouped
depth-12 tied head is `4.182975769 ms`; linear depth-16 accounting plus the
causal allowance is `6.077301025 ms/call`. Measured DFlash verifier cost rises
`1.141709834x` from depth 12 to 16. With the same-distribution measured
`10.664799253` current accepted target tokens and the measured GPU interval
union, the optimistic service threshold is `16.054` accepted target tokens,
or `94.0875%` of the maximum 16-token draft prefix. Perfect acceptance
projects to `0.474599747 s/request`; `16.05` projects to
`0.500232052`, above target.

Interpretation: an analytical path exists only near perfect prefix survival,
but there is no real target-tap disjoint holdout or trained checkpoint. The
project has `$0` provider authority, so no compatible capture/training venue
is in scope. No synthetic acceptance was substituted and no GPU sample was
consumed. The director-bound semantic-localization digest also mismatches the
current cross-project bytes (`7fef...34f2` expected, `7e59...a46b` observed),
so those mutable bytes were not consumed.

Next: director consumes `CAUSAL_PARALLEL_OFFSET_HEAD_RESULT.json`. Reopen only
with positive spend for the single hash-bound capture/train/holdout cycle in
`EXPERIMENT_CONTRACT.json`; do not write READY until the disjoint holdout
clears `16.054` and a matched GPU command exists.
