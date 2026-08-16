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

## Director-authorized H200 component phase — 2026-07-25

The source discriminator passed. Continue this same scientific project with
one exact real-weight H200 component measurement; do not create a successor
project and do not run an endpoint.

### Frozen evidence and runtime binding

- Source terminal:
  `CERTIFIED_LAZY_VOCAB_RESULT.json`,
  SHA-256
  `c4918e00be2225eb326786e3b7975cc8d23a98c5bc0c0c16585b75a742e82210`.
- Candidate source:
  `certified_lazy_vocab_discriminator.py`,
  SHA-256
  `74ca37c0cf39523981b46a83183a3df41493ba55af7010fcc070bcef2a66e104`.
- Raw discriminator:
  `DISCRIMINATOR_RESULT.json`,
  SHA-256
  `abde4d8668581f6f581544448a84ff925587e9f68f5bfa9c1f87fc0bc3f9f7d9`.
- Exact immutable BF16 tied weight:
  `eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa`.
- Exact checkpoint:
  `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Exact consumer geometry: scope-matched 384-row target-verifier hidden
  states and draft proposals from the pinned c32 workload.
- Target runtime:
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`
  on NVIDIA H200 SXM.
- Preferred warm bench:
  `h200-dflash-adapter-e00vyqp7gxsr34wrtz`. It is currently owned by
  `gemma4_hybrid_attention_placement_codesign`; prepare independently and
  claim it only after that owner releases it.

`DIRECTOR_REAL_WEIGHT_H200_BINDING.json` is the machine-readable contract.
Verify its bound hashes before execution.

### Component work contract

Use `$kernel-research` for the exact H200 implementation and measurement.

1. Implement the smallest graph-safe proposal-block certificate plus
   unconditional stock fallback over the exact immutable tied weights.
   Preserve stock row order, accepted-prefix decisions, tokens, ties, and RNG.
2. Prepare and test all source that does not require CUDA before attempting a
   claim. Do not wait or poll for the claimed bench. If it is unavailable,
   preserve a buildable ready artifact and leave the project active.
3. After the preferred H200 is released and has at least 60 minutes of
   lifecycle remaining, atomically claim it for at most 45 minutes. Reuse the
   resident checkpoint, image, compiler, and CUDA caches; do not create or
   mutate provider resources.
4. Measure stock and candidate on the same bound real-weight 384-row consumer
   with CUDA events and enough graph-safe repetitions to report raw rows,
   median, p95, certificate/fallback rates, residency, and launch behavior.
5. Write `LAZY_VOCAB_H200_COMPONENT_RESULT.json` and
   `LAZY_VOCAB_H200_COMPONENT_TERMINAL.json`. A positive component requires
   zero semantic/RNG mismatches, a real-row certificate rate strictly above
   `0.4733361287714464`, a candidate median strictly below
   `4.182975769042969 ms`, and resident-state fit. Otherwise return the exact
   measured negative. Ordinary build or runtime integration defects are
   recoverable project-local repairs, not mechanism evidence.

Endpoint execution, approximate top-k, changed sampling distributions,
quality waivers, and provider lifecycle changes remain forbidden. A positive
component returns to the director for a separate endpoint decision.

### Phase budgets

- Wall clock: at most 90 minutes per researcher invocation.
- H200 claim: at most 45 minutes at `$2.45/hour`.
- Total newly authorized spend: at most `$2.50`.
- Storage: at most 5 GiB of new non-checkpoint artifacts.
