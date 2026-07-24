# Qualified NGRAM sustainable cost surface

## Question

Does the now quality-qualified native-NGRAM H200 endpoint sustain the campaign's
90%-utilization cost target under the exact prompt-heavy cache mix, and what
fresh-input, cache-read, output, and separate 10K single-stream economics does
it actually deliver?

## Evidence

The exact candidate completed c32 at `0.625149101968745 s/request`, below the
`0.6381105231` H200 ceiling. Fresh sequential production validation passed:
both AR and NGRAM scored `55/198` GPQA-Diamond and `10/165` TauBench, while
NGRAM used 18 fewer completion tokens and reduced aggregate capture latency
from `150.420 s` to `85.398 s`.

At the fresh committed H200 planning rate of `$3.25/hour`, the c32 point
analytically corresponds to `1.59961839 request/s`, `$0.123441/M` total tokens
at full utilization, and `$0.137156/M` at 90% utilization. That narrowly beats
the approximate `$0.14/M` market blend, so queue stability, cache realization,
power, failures, and headroom now determine the decision.

## Experiment

Use warm bench `h200-ngram-critical-e00bwcwgsxawx1jmgw`, its resident exact
checkpoint and pinned image, and the qualified NGRAM launch unchanged. Freeze
one deterministic consumer from `EVIDENCE_BINDING.json`.

First run the separate exact 10,000-input/358-output c1 stream once and retain
TTFT and post-first-token rate separately. Then run one bounded open-loop
primary workload at `1.439656551 request/s` (90% of the measured c32 capacity)
for 12 scored minutes after warmup. Generate unique deterministic suffixes
from the validated trace contract while preserving 4,214 input tokens, 358
requested output tokens, a 535-token common prefix, and approximately 12.7%
cacheable prompt share. Do not silently create full-prompt cache hits by
replaying identical requests.

Record submitted and completed requests, exact token counts and hashes,
queue/TTFT/ITL/prefill/decode/completion distributions, cache query/hit deltas,
HBM and allocator state, continuous utilization and power, server restarts,
failures, provider/useful seconds, and actual experiment cost. Report
fresh-input, cache-read, and output cost components separately, then the
campaign blend at the `$3.25/hour` planning rate and `$2.925-$3.60/hour`
sensitivity. Include explicit storage, orchestration, replica/headroom, and
observed reliability factors rather than calling raw GPU cost all-in.

This is candidate-only sustainability evidence, not another AR/NGRAM pair.
Do not replay GPQA, TauBench, the verifier discriminator, or the canonical c32
pair; change NGRAM settings; sweep arrival rates; or add a second workload.
Use a detached durable owner and release by `14:20Z`.

## Decision

The endpoint is sustainably competitive only if every scored request
completes, there is no reload or growing queue over the final two-thirds of
the run, cache accounting matches the trace contract, and measured
90%-headroom economics remain competitive with the `$0.14/M` blend after
observed reliability plus explicit operating-cost sensitivity. Preserve the
10K methodology view separately. A miss closes the current H200 placement,
not the qualified NGRAM semantics.

## Resources

- Priority: `7000`
- Researcher profile: `execution`
- Authorized cumulative spend: `$5`
- Compute: retained H200, at most 60 claimed GPU-minutes
- Wall clock: release by `2026-07-24T14:20:00Z`
- Storage: at most 12 GiB of new artifacts
- Provider mutation: forbidden
