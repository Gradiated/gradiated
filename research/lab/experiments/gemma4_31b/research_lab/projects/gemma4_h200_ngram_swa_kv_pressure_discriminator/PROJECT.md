# NGRAM SWA/KV pressure-transition discriminator

## Question

Does the request-809 service collapse come from an occupancy-dependent
SWA/KV cache, allocator, or batch-topology transition, and can one
source-justified pressure policy keep the fixed NGRAM arrival stream
sustainable without changing served semantics?

## Why this is the next bottleneck

The qualified NGRAM stack already delivered `6,489-6,499 tokens/s` and raw
planning cost of `$0.138905-$0.139109/M`, but both complete 1,036-request
trajectories accumulated `6.432-8.148 s` of client backlog. Corpus reset was
a clean negative: the trie was only `552/10,000,000` nodes and corpus work was
far too small to explain the phase change.

The remaining transition is sharply localized. HBM first grew at about
request 809, then rose from about `123,436` to `128,514 MiB` by request 853.
At the first step there were 14 running requests, only 737 SWA tokens
available, 26,828 SWA tokens used, 170,467 evictable SWA tokens, 48,198 full
KV tokens available, and 3.35M cumulative evictions. Requests 800-999 then
held roughly `22-23 s` mean latency while the server queue remained zero.
This is the unresolved causal boundary that controls sustainable economics.

The just-closed production QLEN realization does not compete with this line:
its real two-stage component was exact but bounded at only `+0.142679%`, and
its sole endpoint changed service time by `-0.011674%` while lacking the
required token comparator.

## Experiment

Consume and hash-check `DIRECTOR_BINDING.json`. Inspect only the bound SGLang
SWA radix cache, full KV pool, token allocator, scheduler admission/retraction,
and CUDA/PyTorch allocation sources plus the persisted transition evidence.
Map the exact ownership and allocation event that can produce the request-809
HBM staircase. Record allocated, reserved, and non-releasable device bytes;
SWA/full-KV used, available, evictable, locked, and reclaimed tokens; prefix
refcounts; batch request/token geometry; retractions; target-verification
time; acceptance; HBM; power; and client/server queue state.

Before claiming the H200, freeze exactly one falsifiable intervention tied to
that source path. It may change only cache reclamation/allocation timing or
pressure-aware admission at the measured SWA/KV boundary. It must not change
request bytes or schedule, model/checkpoint, FP8 representation, page-1 E5M2
KV, NGRAM tree/draft settings, target-verification semantics, M64 attention,
context length, or the configured maximum-running ceiling. A generic
concurrency, wave, QLEN, ring, corpus, backend, or threshold sweep is
forbidden. If source inspection cannot bind a single actionable mechanism,
finish with that typed causal terminal without claiming a GPU.

Claim warm `h200-ngram-verifier-e00kcm9nfhwt7e7gbc` once. Reuse its checkpoint,
image, JIT, tokenizer, and runtime caches. Run one candidate-only 1,036-request
trajectory against the persisted controls; do not replay stock, state-aging,
wave, quality, 10K, c32, or any component. The controller-host outer owner
must be PID-managed, keep claim heartbeats and repair handshakes local, and
use `research/factory/tools/artifact-snapshot` for every retrieval. Ordinary
source installation, permissions, telemetry, and consumer defects stay inside
this project and may repair only the invalidated stage under the same claim.

## Decision

Retain the mechanism only if all 1,036 arrivals complete with zero failures,
every output token sequence, finish reason, and usage matches the bound
index-aligned target-verified comparator, no upstream queue or retraction is
introduced, and the final client queue is at most one arrival spacing
(`0.6946101133 s`) with non-positive late-window trend. Require raw planning
cost at or below `$0.14/M` at `$3.25/H200-hour`, and require counters to show
that the measured request-809 allocation/pressure transition is removed or
moved consistently with the intervention.

If the pressure event remains while the intervention is active, or service
stability/economics/semantics fail, close this exact mechanism. Preserve the
source and counter localization for the next materially different line; do
not tune the threshold or switch interventions inside this project.

## Resources

- Priority: `7600`
- Researcher profile: `deep`
- Authorized cumulative spend: `$8`
- Bench: retained `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`
- Compute: at most 80 claimed H200-minutes
- Wall clock: finish and release by `2026-07-24T20:50:00Z`
- Storage: at most 12 GiB of new project-local artifacts
- Provider mutation: forbidden
