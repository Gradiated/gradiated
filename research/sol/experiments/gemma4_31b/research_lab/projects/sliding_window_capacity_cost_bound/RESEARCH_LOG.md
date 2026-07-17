# Research log

## 2026-07-17 — director delegation

Delegated as a disjoint `$0` model-change screen while the exact-shape L40S owner remains exclusive for provider mutation. Bound exact residency and attention work for shorter local windows, preserve the 1,024-token control and all authoritative allowances, and nominate at most one later quality-gated candidate. Do not touch or wait for the live owner and do not add another retained-session arm.

## 2026-07-17 — deterministic window matrix complete

Question: can a shorter local window make BF16-KV c8 fit or retain a >=5% whole-request work mechanism?

Action: ran `calculate_window_bound.py` against the pinned geometry, memory, FP8-KV, and vLLM source inputs. It computes BF16 and source-specified FP8-per-token-head logical K/V residency for c1/c4/c8/c16, plus exact hybrid QK/AV work for 4,214/358 and preserves the 39.350 GiB non-KV allowance and 44.704 GiB envelope. No CUDA, provider, checkpoint, live-owner, or retained-session action occurred.

Evidence: BF16 c8 peak residency is 45.266 GiB at 1,024 tokens and 44.484 GiB at 768; 512 and 256 are 43.703 and 42.922 GiB. The theoretical whole-request QK/AV upper bounds are 0.5440%, 1.1258%, and 1.7455%, respectively, after projections/MLPs/vocabulary work remains in the denominator. `WINDOW_BOUND.json` also records the FP8 source-byte reconciliation for the separate conditional arm.

Interpretation: nominate 768 only as the least-disruptive quality-gated capacity candidate. It is not a speed/cost claim and none of the windows clears 5% work relevance. No second candidate or live-owner arm is created.
