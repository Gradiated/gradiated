# Gemma 4 exact proposal ensemble

## Question

Can a causal ensemble of prompt lookup, output-history multi-order NGRAM, and
prior-request cache proposals reduce target verification work by at least 20%
relative to native depth-12 NGRAM on the exact Gemma 4 workload?

## Why this matters

The current quality-qualified NGRAM stack is the strongest measured route, but
another 20% cannot plausibly come from mask staging alone. Increasing accepted
tokens per target pass compounds with every verifier optimization and remains
target-semantic by construction: proposed tokens are emitted only after target
verification.

Use `$researcher` and `$experiment-run`. This is a causal trace experiment, not
a literature report or a new quality campaign.

## Immediate experiment

Build a deterministic, leakage-safe replay over locally captured prompt and
completion token sequences. At each generated position, proposals may use only
the current request's prompt, its already-emitted output prefix, and earlier
requests in chronological order. Compare:

1. the current native depth-12 output-history NGRAM rule;
2. longest causal prompt-copy continuation;
3. multi-order output-history NGRAM with deterministic tie-breaking;
4. the best deterministic ensemble of those sources;
5. optionally, a bounded earlier-request cache if it adds independent coverage.

Report accepted-length histograms, target passes per emitted token, proposed and
verified rows, no-match frequency, lookup CPU cost, working-set size, and
results split by workload segment. Use the 791-row endpoint trace for campaign
geometry and locally captured GPQA-Diamond/TauBench traces with sufficient
prompt/output token identity as an anti-overfit check. Do not infer a serving
speedup from synthetic repetitive rows alone.

If a causal candidate removes at least 20% of target passes or target rows
without pathological lookup cost on both useful scopes, implement the narrow
v0.5.15 proposal-source change and exact CPU fixtures in this project. Then
request a compatible H100/H200 bench for one target-hardware component and
endpoint pair. If no candidate reaches that bound, preserve the measured
acceptance surface and close this route without GPU spend.

## Contract

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime target: SGLang `f63458b5beaceabbd9d749b9fc956370e1b649e6`.
- Primary inputs:
  `../gemma4_h100_v0515_ngram_price_normalized/packet/candidate-v0.5.15/inputs/requests.jsonl`
  and `exact_semantic_rows.jsonl`.
- Correctness: causal information boundaries must be mechanically enforced;
  every proposed token remains subject to unchanged target verification.
- Economic goal: a credible combined route from the current qualified
  `0.62514910197 s/request` result toward `0.50011928158 s/request`.
- Spend: `$0` in this stage. Researchers must not create or mutate providers.
- Timeout: four hours for the replay, implementation, and decision.
- Artifacts: immutable input manifest, replay code, fixtures, per-row proposal
  and acceptance results, summary, source patch if promoted, and concise log.

