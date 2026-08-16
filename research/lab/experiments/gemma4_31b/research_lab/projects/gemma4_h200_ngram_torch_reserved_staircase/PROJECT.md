# NGRAM PyTorch-reserved staircase attribution and reuse

## Question

Which concrete CUDA-graph pool, target-verification workspace, or
batch-topology tensor allocation creates the 5.96 GB PyTorch-reserved/HBM
staircase beginning near request 809, and can one ownership-specific reuse or
preallocation change remove the associated service collapse?

## Why this is the next bottleneck

The exact page-aligned SWA leaf split reduced SWA occupancy at the transition
by 9,170 tokens (`34.18%`) and capped every observed locked leaf at 1,023
tokens. The transition nevertheless began at request `809.86` with 14 running
requests, HBM grew `5,166 MiB`, and PyTorch reserved bytes grew
`5,960,105,984`. The fixed stream then accumulated `9.184 s` of client release
drift and cost `$0.140065/M`, despite exact semantics and zero server queue or
retractions.

This separates two effects: excess leaf locking is real secondary pressure,
but it does not own the collapse. The scope-matched growth of PyTorch reserved
memory and HBM as active batch topology expands now points to lazy graph
pools, target-verification workspaces, or topology-shaped tensors. Identifying
that allocation owner has higher information value than another cache
threshold or admission-policy guess.

## Experiment

Consume and hash-check `DIRECTOR_BINDING.json`. Claim the retained H200 once.
Before stopping the healthy retained server, capture the exact installed
PyTorch/SGLang scheduler, CUDA-graph, NGRAM target-verification, attention,
and allocator-facing sources read-only. Restart from the clean pinned image
with stock SWA-radix behavior; do not retain the rejected leaf-split
environment variable.

Run one bounded attribution trajectory over the exact scheduled prefix through
request 870. Enable the narrowest allocation-history and stack capture that
can bind the request-780-to-870 reserved-memory growth without broad profiling
or unbounded snapshots. Correlate allocation address/size/stack and graph-pool
identity with active batch size, target-verification shape, SWA/full-KV
metrics, HBM, and request index. Persist a compact site-ranked attribution.

Only if one concrete allocation owner accounts for a material part of the
`5.96 GB` staircase and admits a narrow semantics-preserving repair, freeze
exactly one intervention in the same project. Allowed forms are:

- reuse of a topology-shaped target-verification workspace;
- preallocation/capture of the same required storage before scheduled
  arrivals when the measured harm is lazy allocation/capture;
- release or sharing of a proven dead graph/workspace pool.

Do not guess among these forms before attribution. Do not change request bytes
or schedule, max-running 32, model/checkpoint, FP8 representation, page-1
E5M2 KV, NGRAM tree/draft settings, target-verification semantics, attention
backend/tile, or context. Run no cache, graph-batch, workspace-size,
concurrency, or threshold sweep.

If an intervention is admitted, run one candidate-only complete
1,036-request trajectory against the persisted exact comparator. Replay no
stock, leaf-split, state-aging, wave, QLEN, ring, quality, c32, or 10K arm.
Use one controller-host PID-managed owner, retain claim heartbeats and repair
handshakes locally, and use `research/factory/tools/artifact-snapshot` for
each retrieval. Ordinary source installation, permissions, and telemetry
defects remain repairable under the same claim.

## Decision

The attribution stage is decision-bearing even if no candidate is admitted:
require allocation-stack and pool identities whose byte totals reconcile
materially with the measured staircase. Reject non-actionable or diffuse
ownership without spending the conditional full trajectory.

Retain a conditional intervention only if all `1,036/1,036` requests complete
with exact output-token sequences, finish reasons, and usage; no failures,
retractions, or final server queue; client release drift at most one arrival
spacing (`0.6946101133 s`); non-positive queue trend across the final 100
requests; and planning cost at or below `$0.14/M` at `$3.25/H200-hour`.
Require the attributed allocation bytes and request-809 HBM transition to be
removed or moved as predicted. A mere prewarming shift that leaves sustainable
throughput unchanged is a negative.

## Resources

- Priority: `7700`
- Researcher profile: `deep`
- Authorized cumulative spend: `$6`
- Bench: retained `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`
- Compute: at most 50 claimed H200-minutes
- Wall clock: finish and release by `2026-07-24T20:50:00Z`
- Storage: at most 12 GiB of new project-local artifacts
- Provider mutation: forbidden
