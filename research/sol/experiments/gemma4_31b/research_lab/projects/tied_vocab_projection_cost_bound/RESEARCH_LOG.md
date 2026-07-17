# Research log

## 2026-07-17 — director delegation

Delegated as a disjoint `$0` model-change falsifier while the paid exact-shape project prepares its one post-cleanup correction. Bound the maximum whole-request and capacity value of isolated tied-vocabulary representation or shortlist changes; preserve tokenizer/output semantics and nominate at most one candidate only on a conservative 5% or capacity gate. Do not touch or wait for the paid lane.

## 2026-07-17 — exact bound closes the line

Question: can the tied `262,144 x 5,376` vocabulary projection clear 5% whole-request relevance or unlock a necessary L40S capacity tier?

Action/evidence: ran the deterministic metadata-only `run_bound.py` using the exact geometry, FP8 memory accounting, and L40S gate inputs. The matrix is 1,409,286,144 parameters: 2.625 GiB BF16, 1.3125 GiB at one byte/parameter, and 2,818,572,288 FLOPs per logits position. With 4,214 prompt / 358 output tokens, an optimistic perfect elimination of all vocabulary logits saves only 0.3750% of decoder plus required logits FLOPs; with 10K input it saves 0.1659%. Reduced-vocabulary proxies from 131K through 4K rows remain 0.1875%–0.3692% on the primary slice.

Interpretation: output-only FP8/INT8 duplicates the tied matrix because input embedding remains BF16, adding 1.3125 GiB and taking conservative primary c8 residency to 46.3585 GiB, above the 44.704 GiB L40S envelope. Joint one-byte tied storage would be 43.7335 GiB and fit, but it changes input and output numerics and has no pinned execution-equivalent consumer. Shortlists violate full-vocabulary correctness and tokenizer/logprob/sampling/API constraints. These are derived ceilings, not throughput, quality, or endpoint-cost measurements.

Decision/next move: close with no nominee and no paid arm. See `VOCAB_BOUND.json` and `DECISION.md`; do not wait for or modify the paid owner.
