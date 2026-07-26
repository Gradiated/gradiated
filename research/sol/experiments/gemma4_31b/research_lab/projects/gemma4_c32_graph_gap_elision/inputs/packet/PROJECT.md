# Persistent grouped decode-equivalent LM head

## Question

Can the qualified native-NGRAM verifier preserve the target decisions of its
12 independent batch-32 BF16 tied-vocabulary projections while reducing their
repeated launch and weight-stream cost through one grouped, persistent, or
otherwise weight-reusing exact-consumer dataflow?

## Why this matters

The qualified stack serves the exact c32 workload at
`0.625149101968745 s/request`; the campaign target is
`0.500119281574996 s/request`. Its semantic repair intentionally reshapes the
384 verifier rows into 12 independent `[32, 5376] x [5376, 262144]`
projections because the native M=384 projection changed temperature-zero
target decisions. A later exact trace measured 180 decode-shaped LM-head GEMM
calls over 15 target-verification steps, totaling `124664.394 us`. This is a
measured, independent residual boundary: attention tiling and adaptive draft
depth do not remove the repeated tied-vocabulary projection.

The rejected one-materialization intervention does not close this question.
It preserved 12 projections, was slower, and changed endpoint text. This
project must instead preserve the qualified per-depth target decisions while
changing the projection execution/dataflow itself.

## Scope and immediate evidence

Use `$kernel-research`. Work offline while the priority-8490 mixed-attention
project owns or awaits the resident H200. Bind the exact qualified verifier
source, model geometry, trace attribution, runtime image, checkpoint identity,
and c32 runner from `DIRECTOR_BINDING.json`.

First explain the physical path from 12 M=32 projections through the BF16 tied
embedding weight to the H200 kernels: launch count, tiles, accumulator order,
weight bytes, L2/HBM reuse, register/shared-memory limits, and the reason the
native M=384 path changes target decisions. Implement one discriminating
candidate, such as a grouped or persistent projection that keeps independent
M=32 numerical domains while reducing launch or weight-stream overhead. The
researcher may choose a better source-justified realization, but may not
restore the semantically rejected native M=384 projection or approximate the
vocabulary without a correctness proof.

Build an exact-consumer component with the production shapes:

- 12 depths, batch 32, hidden size 5376, vocabulary 262144;
- BF16 tied embedding/LM-head weights and production activation layout;
- H200 SXM and pinned SGLang v0.5.13 runtime;
- output comparison including top-two logits, argmax IDs, accepted target
  decisions, launch identity, and repeated-run determinism.

Only a correct, reproducibly faster component with a credible positive
whole-request bound may claim the released H200 for one matched profiler-off
c32 endpoint pair. Require 32/32 completion, exact request hashes, target and
emitted token IDs, finish reasons, usage/cache accounting, NGRAM proposal and
acceptance telemetry, service time, p95, failures, and clean shutdown.

## Decision

Retain a simple positive result even below 5% when the endpoint is exact and
the operational complexity is credible. Close only the tested realization if
it is slower, cannot preserve target decisions, or its physical bound is
dominated by the two higher-priority lanes.

## Resources

- Priority: 8480
- Researcher profile: `deep`
- New spend authority: `$5`
- Compute: at most 90 claimed H200 minutes at `$2.45/hour`
- Storage: at most 6 GiB of new artifacts; reuse checkpoint and image bytes
- Wall clock: release by `2026-07-25T21:45:00Z`
- Bench: sequential reuse of
  `h200-dflash-adapter-e00vyqp7gxsr34wrtz` only after priority 8490 releases
- Provider mutation: forbidden

Do not delay or rewrite either active GPU project. If the H200 is unavailable,
continue only bounded offline source, implementation, compile preparation, and
analytical work; do not create another provider bench.
