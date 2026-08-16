# NGRAM verification critical path

## Question

After the quality decision releases the retained H200, can one source-level
change to the measured native NGRAM verification critical path reduce
sustainable c32 cost per completed request beyond
`0.625149101968745 s/request` without changing accepted tokens, feature
semantics, or the frozen NGRAM contract?

## Why this is independent

The production-validation project decides model and tool quality. This project
asks a separate accelerator/runtime question: where the target-verified
candidate spends non-overlapping GPU and scheduler time, and whether one
source-justified overlap, launch, dataflow, or verification change can remove
that cost. The current candidate clears the campaign ceiling narrowly, so a
small exact gain compounds directly into price headroom.

Generic concurrency and flag sweeps are closed: c48 and c64 were already
negative on the non-speculative FP8 baseline. This project must profile the
exact NGRAM candidate and implement one causal mechanism; it may not substitute
a load sweep.

## Experiment

Work offline while priority-6800 owns or awaits the H200. Bind the exact
candidate terminal, launch, runner, model, image, checkpoint, and source
symbols. Prepare one Nsight Systems capture contract plus only the minimum
kernel counters needed to distinguish the top non-overlapping boundary.

The director provisioned independent bench
`h200-ngram-critical-e00bwcwgsxawx1jmgw` so this project does not serialize
behind priority-6800. Atomically claim it and run one bounded profiler capture
of the exact c32 NGRAM endpoint. Attribute wall time across draft lookup,
target forward/verification, accepted-token bookkeeping, sampling/LM head,
cache/position updates, graph launches, scheduler/host gaps, and serialization.
Then implement exactly one source-level intervention justified by the dominant
measured boundary and run a matched profiler-off c32 control/candidate pair.

The intervention must preserve the exact target, runtime stack, NGRAM settings,
request bytes, accepted token sequence, parsed tool semantics, finish reason,
usage accounting, 32/32 completion, and server stability. No assistant model,
new corpus, sampling change, NGRAM-parameter sweep, generic flag sweep, or
second intervention is allowed.

## Decision

Retain the intervention when the matched pair is complete and valid, candidate
service time is lower, p95 completion time does not regress materially,
accepted/served semantics match, and the change improves all-in cost per
completed request after reliability and headroom. A null attribution or
non-positive matched pair closes only the measured intervention, not NGRAM
quality or the broader campaign.

## Resources

- Priority: `6790`
- Researcher profile: `deep`
- Authorized cumulative spend: `$8`
- Compute: one independent H200, at most 105 claimed GPU-minutes
- Wall clock: complete and release by `2026-07-24T14:20:00Z`
- Storage: at most 12 GiB of new project-local artifacts
- Provider mutation: forbidden
