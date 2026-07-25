# Certified lazy vocabulary head

## Decision question

Can the exact Gemma 4 31B c32 serving path replace routine materialization of
the dense 262,144-way output with a certified lazy consumer that evaluates
only the vocabulary blocks needed for exact speculative acceptance or
sampling, falls back to the stock head when certification is inconclusive,
and has a credible net H200 saving?

This project is deliberately separate from the closed exact
grouped-projection realization. It changes the producer/consumer contract and
may use a static hierarchy or index over the immutable tied output weights; it
must not claim value from making the same dense projection faster.

## Hypothesis and early discriminator

The tied output-weight geometry and the high accepted-draft depth of the exact
NGRAM workload may permit lossless block bounds, exact lazy rejection
sampling, or another certified method to avoid most dense-logit evaluation.
The first cycle must determine whether the stock acceptance and sampling
semantics fundamentally require the exact full partition function on every
row. If they do, and no mathematically exact alternative consumer removes that
dependency, return a typed negative result rather than proposing an
approximation.

## Bound evidence

- Campaign denominator: `0.625149101968745 s/request`.
- Campaign target: at most `0.500119281574996 s/request`.
- Exact source inputs:
  - `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json`
    (`e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`)
  - `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/logits_processor.py`
    (`e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14`)
  - `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/forward_batch_info.py`
    (`c977296f3b90be69fff5312f2b3af7699a17b20af24614b139f69888e5776516`)
- The prior exact grouped endpoint control observed mean accepted speculative
  length `10.6648/12`; treat this only as scope-matched measured motivation,
  not as evidence that lazy evaluation is feasible.

## Work contract

Use `$kernel-research` for the exact-shape kernel/dataflow analysis.

1. Trace the stock SGLang producer and every exact speculative-acceptance,
   rejection, final-sampling, softcap, logprob, row-order, and RNG consumer.
2. State the minimum information each row requires. Distinguish accepted
   draft rows from rejection and final-sampling rows; do not assume that a
   token logit alone is sufficient.
3. Construct the smallest mathematically exact lazy algorithm that could
   satisfy those consumers, including certification, fallback, indexing
   cost, and immutable tied-weight lifecycle. If none exists, prove the
   dependency that prevents it.
4. Build a deterministic CPU/reference simulator or equivalent executable
   discriminator over bound weights or synthetic geometry. It must compare
   token decisions and RNG consumption against the stock rule.
5. Produce an analytical H200 c32 bound covering weight traffic, hidden-vector
   traffic, reductions, index residency, logits avoided, launches, divergence,
   fallback rate, CUDA-graph constraints, and preprocessing amortization.

Evidence must be labelled measured, analytical, derived, inferred, or
synthetic. Do not transfer a result from another model, workload, or
accelerator.

## Quality gate and terminal

Write `CERTIFIED_LAZY_VOCAB_RESULT.json` with a typed result:

- `source_complete_candidate`: exact stock-consumer trace, executable
  equivalence discriminator, explicit certification/fallback contract, and a
  positive conservative H200 net bound; or
- `mechanism_falsified`: the exact-normalization or physical-cost dependency
  that defeats the mechanism, with the failing evidence preserved.

No approximate top-k, changed sampling distribution, token mismatch, altered
RNG consumption, endpoint claim, or quality waiver is admissible.

## Budgets and stop rules

- Wall clock: at most 90 minutes.
- Compute: CPU/source analysis only; no accelerator claim.
- Storage: at most 2 GiB of new durable artifacts.
- Spend: `$0.00`.
- Provider mutation: forbidden.

Stop this cycle after the typed terminal. A positive result prepares a
separate director-authorized exact component measurement on a compatible
resident bench; it does not authorize one.
