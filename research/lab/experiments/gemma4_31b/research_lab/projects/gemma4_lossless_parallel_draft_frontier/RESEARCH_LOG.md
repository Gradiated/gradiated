# Research log

## 2026-07-26 — A/A first divergence, repair, and measured frontier

- Question: can the existing Gemma DFlash drafter plausibly deliver the required 20% lossless service reduction after repairing its first semantic divergence?
- Action: consumed no new sample. Replayed immutable request-25 state and two same-source/same-workload candidate terminals, applied the exact `direct_carry_valid=False` patch to the pinned source, and reconstructed accepted work for retained c32 depths 4/8/12/16 from cumulative SSE against the persisted CUDA-event costs.
- Evidence: the observer A/A is byte-identical; runtime A/A matches only 23/32 request token streams. Positional direct carry misroutes the real request-25/request-28 `verified_id/new_seq_lens` state after reorder, while FutureMap preserves ownership. The patch produces the already content-addressed repaired source SHA-256 `eb976179a5ec54d607bfaf66e087c04d1c39617f312c105081974a3a8aa9de08`. Depth 4 wins at `521.915953` accepted target tokens per CUDA-event-second and `3.006316` accepted target tokens per verification. The completed paired endpoint improved only `1.134946%` (`1.528631381` to `1.511282239 s/request`) and was semantically divergent.
- Interpretation: the ownership repair is working source, but it cannot create the missing accepted work. The current drafter/runtime is `typed_none` for the 20% target. Raw verifier logits were not persisted, so no GPU-executed repair claim is made.
- Next: if speculation remains in the portfolio, train and falsify the separate Gemma causal parallel-offset head described in `PARALLEL_DRAFT_FRONTIER.json`; do not replay the retained endpoint/depth samples.
