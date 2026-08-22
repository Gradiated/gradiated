# Lossless output-head low-rank residual index

## Question

Can a query-asymmetric low-rank projection plus conservative per-row residual
certificates reject a material physical union of Gemma 4's 262,144 output
rows while preserving the exact pinned greedy sampler set?

## Why it matters

The exact output head accounts for about `0.0351006 s/request`, but two
geometric bounds have now failed physically: fixed-coordinate
residual-Cauchy avoided only `3.7458%` of union bytes, and full-vector
centroid/radius clustering avoided none. A learned projection can concentrate
the query-aligned score before applying an exact residual certificate and is
materially different from both rejected balls and fixed coordinates.

## Exact scope

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Reuse the predecessor's exact tied BF16 output weights and the same 32
  hidden rows read-only.
- Preserve the recovered stock consumer: temperature-zero greedy argmax,
  monotone softcap, and min-token stop masking. Top-1 preservation alone is
  insufficient unless it proves the entire possible stock candidate set.
- Candidate: one deterministic low-rank or product-subspace score bound whose
  residual term is conservative under stock BF16 accumulation/output
  rounding. The index may reorder or duplicate weights only when physical
  storage and traffic are charged.
- Evaluate 32-row physical union traffic, metadata, projected query traffic,
  survivors, exact verification traffic, and any additional tied-weight
  storage. Do not report logical pruning as physical savings.

## Immediate experiment

Use `$researcher` with deep profile and `$experiment-run`. Read the predecessor
`LOSSLESS_CLUSTER_MIPS_TERMINAL.json` once and reuse its exact inputs. Build
one cheap spectrum/residual discriminator first. If even an oracle incumbent
cannot avoid at least 10% of physical union weight bytes before metadata,
terminalize the representation without a parameter sweep. Otherwise implement
one conservative index and report exact stock-set containment plus net bytes.

## Limits

- Wall clock: 45 minutes.
- GPU/provider spend: `$0`; never claim the warm H200.
- Additional storage: 4 GiB.
- Do not mutate the QKV project or reopen centroid/radius and fixed-coordinate
  bounds.

## Portfolio-changing result

Promote only if exact stock-set containment holds and net physical bytes fall
materially after all metadata and verification traffic. A falsification
closes this low-rank residual representation, not learned quality-recovered
heads or the campaign.
