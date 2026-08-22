# Output-head product-quantized MIPS recovery proxy

## Question

Can a compact product-quantized full-vocabulary inner-product scan retrieve a
small candidate set that contains every stock Gemma 4 greedy-sampler candidate
on held-out hidden rows, while exact BF16 rescoring of that set uses
substantially less physical traffic than the dense 262,144-row output head?

## Why it matters

The output head accounts for about `0.0351006 s/request`, or 5.61% of the
qualified `0.625149101968745 s/request` endpoint. Three lossless certificate
families now fail physically on disjoint queries: fixed-coordinate
residual-Cauchy avoided 3.75% of union bytes, full-vector cluster radii avoided
none, and the frozen rank-32 residual index retained 262,143 of 262,144 rows
and increased fully charged traffic by 13.53%.

Those negatives reject conservative envelopes, not compressed approximate
ranking. Product-quantized asymmetric MIPS can scan every token using a small
code, then read exact BF16 weights only for a shortlist. This intentionally
relaxes universal losslessness and is a quality-recovery proxy, not a
deployable model result.

## Hypothesis and control

- Stock control: the exact tied BF16 output head and recovered
  temperature-zero greedy consumer, including monotone softcap and min-token
  stop masking.
- Hypothesis: one fixed product-quantized weight index can preserve the full
  possible stock candidate set on held-out capture rows at a shortlist small
  enough that compressed-code scan, lookup tables, candidate IDs, exact
  survivor weights, and exact logits remain net traffic-positive.
- Falsifier: every preregistered shortlist either misses a stock candidate or
  loses its physical traffic advantage after complete accounting.

## Exact inputs and workload

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Read
  `../gemma4_lossless_output_head_lowrank_residual_disjoint_query/LOSSLESS_LOWRANK_RESIDUAL_DISJOINT_TERMINAL.json`
  and
  `../gemma4_lossless_output_head_cluster_mips/inputs/EXACT_CAPTURE_TERMINAL.json`
  once.
- Reuse the exact tied BF16 weights and 1,536-row, 32-request hidden-state
  capture read-only. Deterministically select two c32 batches (64 rows total)
  that exclude every row used by the preceding low-rank fit and held-out
  discriminator; persist the row provenance and disjointness hashes.
- Train codebooks from output-weight rows only. Freeze the index before
  scoring hidden rows. Hidden rows, shortlist geometry, and reported operating
  point must not influence codebook fitting.

## Immediate experiment

Use `$researcher` with deep profile and `$experiment-run`.

1. Build one deterministic product-quantized asymmetric inner-product index.
   Choose its code width analytically before evaluation; do not run a
   codebook-geometry sweep.
2. Evaluate the preregistered exact-rescore shortlist sizes 256, 1,024, and
   4,096 on both c32 batches.
3. For each size, report complete stock-candidate recall, exact greedy-output
   agreement after BF16 rescoring, miss margins, physical union rows, and
   fully charged bytes: PQ codes, codebooks, query lookup tables, score
   buffers, candidate IDs, exact member weights, and exact logits.
4. Publish `OUTPUT_HEAD_PQ_MIPS_PROXY_TERMINAL.json` with immutable input and
   index hashes plus a typed promote/close decision.

Do not add a lossless residual certificate, tune after observing held-out
rows, or claim general quality from this capture.

## Quality, latency, and promotion

This proxy passes only when one preregistered shortlist contains the complete
possible stock candidate set for all 64 held-out rows and remains positive on
fully charged physical traffic in each c32 batch. Report the analytical
byte-proportional upper bound against the 0.0351006-second output-head interval;
do not report CPU runtime as endpoint latency.

A pass promotes one target-H200 exact-consumer component and later
GPQA-Diamond/TauBench recovery work. It does not establish production quality.
A miss or net-traffic failure closes this fixed PQ retrieval proxy while
leaving trained or hierarchical approximate heads open.

## Limits

- Reentry wall clock: 65 minutes, ending no later than
  `2026-07-29T21:05:00Z`.
- GPU/provider spend: `$0`; do not call `gpu_pool`, SSH, Docker, CUDA,
  endpoint traffic, or provider APIs.
- Additional storage: 4 GiB.
- Do not mutate any predecessor or the QKV endpoint project.
