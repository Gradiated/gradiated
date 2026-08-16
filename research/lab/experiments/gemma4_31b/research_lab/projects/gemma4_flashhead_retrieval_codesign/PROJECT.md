# Gemma 4 large-vocabulary head co-design

## Question

Can Gemma 4's 262,144-way tied output projection be replaced by a
hardware-efficient clustered/retrieval head that removes a material fraction
of head compute while retaining enough target-distribution fidelity to remain
a credible OpenRouter model?

## Why this matters

The qualified native-NGRAM trace contains 180 depth-sliced tied-head launches
over 15 verifier cycles. The independent exact grouped-projection project can
reduce launch and weight-stream cost but preserves all 262,144 logits.
FlashHead reports up to 1.75x model-level inference speedup on Gemma-3 and
other model families by replacing dense vocabulary classification with
balanced clustered retrieval, multiprobe search, selective quantization, and
full-distribution sampling. This project tests that larger architectural
mechanism rather than duplicating the exact grouped kernel.

## Immediate deep-research cycle

Use `$researcher` and the recent landscape evidence. Reconstruct the exact
Gemma tied-head geometry, token-frequency and embedding structure, runtime
consumer path, and measured head attribution. Determine the smallest
production-shaped design that can answer:

1. how many clusters/probes are needed to recover the dense head's top-1,
   top-k, and target-verifier decisions on representative campaign hidden
   states;
2. whether cluster scoring plus candidate scoring reduces H200 bytes, tensor
   work, and launch count after accounting for index/retrieval overhead;
3. whether the same representation can support temperature-zero generation
   first and later OpenRouter sampling without materializing all logits.

Implement a bounded offline prototype or simulator using available persisted
hidden-state/logit fixtures. If representative hidden states are absent,
identify the smallest later capture needed; do not turn capture preparation
into the project result. Compare against both the qualified 12xM32 dense head
and the independent exact grouped candidate.

This is an exploration project. Exact-token equality is not required of the
architectural candidate, but top-k recall, verifier-decision divergence, and
estimated whole-request opportunity must be explicit. Do not claim quality
preservation from the paper or simulator. A promising candidate will later
need a measured component followed by GPQA-Diamond and TauBench.

## Result that changes the portfolio

Persist working code and a concise decision containing:

- exact representation and search geometry;
- recall/divergence curve versus candidate count and probes;
- measured or tightly derived component and whole-request bound;
- predicted H200 counter change;
- the minimum component experiment needed next.

Continue only if a credible configuration has materially more upside than the
exact grouped-projection lane at acceptable divergence, or if a narrow
post-training step has a plausible recovery path. A negative result should
identify whether the limiter is recall, retrieval overhead, head attribution,
or tied-weight/model semantics.

## Resources

- Researcher profile: `deep`
- New provider spend: `$0`
- GPU claims and provider mutation: forbidden in this cycle
- Local artifact budget: 4 GiB
- Primary evidence:
  `../../evidence/RECENT_INFERENCE_RESEARCH_LANDSCAPE_2026-07-25.md`
- Paper: <https://arxiv.org/abs/2603.14591>

Use judgment and produce evidence or working source; do not write a second
literature review.
