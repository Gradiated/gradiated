# NGRAM M384 FP8 cluster schedule

## Question

Can the qualified H200 NGRAM endpoint reduce target-verification FP8 linear
time by changing only the exact `M=384` CUTLASS CTA-cluster orientation from
stock `2 x 1 x 1` to `1 x 2 x 1`, while preserving exact model and serving
semantics?

## Evidence and mechanism

The repaired exact-c32 NGRAM trace contains a fixed target-verification
geometry of `32 requests x 12 draft rows = M384`. Its stock FP8 CUTLASS
kernel uses a `128 x 128 x 128` tile and a `2 x 1 x 1` CTA cluster. Three
128-row M tiles cannot fill the final two-CTA M cluster. The output-N
dimensions of the real QKV, gate/up, and down projections provide many tiles,
so a `1 x 2 x 1` cluster can preserve a two-CTA Hopper cluster and the stock
ping-pong fast-accumulation kernel while moving the cluster tail away from M.

The trace reports `1.163217634` seconds of summed FP8 CUTLASS kernel time in a
`3.165732460` second trace window. This is relevance evidence, not an
additive wall-time attribution. It is the second-largest GPU family after
target-verification attention. The retained c32 wave topology is especially
well matched to the fixed shape: the completed trajectory reported
`spec_accept_length=11.828571` and `spec_accept_rate=0.984416`, so reducing
draft depth is not supported in that topology.

This is distinct from the closed dense-FP8 schedule arm. That arm changed the
cluster from `2 x 1 x 1` to `2 x 2 x 1` at prefill M values
`1409/1631/2048`; it did not test M384 or an N-oriented two-CTA cluster. It is
also distinct from variable-row compaction, QLEN masks, attention tiles, and
wave admission.

## Experiment

Use `$kernel-research`. Hash-check `DIRECTOR_BINDING.json`, inspect the pinned
SGLang/CUTLASS selection path, and first prove that the live qualified
target-verification consumer invokes the bound FP8 kernel at M384. Freeze one
candidate:

- select `1 x 2 x 1` only for the exact M384 FP8 target-verification linear
  path;
- preserve the `128 x 128 x 128` tile, ping-pong fast-accumulation schedule,
  scaled epilogue, E4M3 weights/activations, BF16 outputs, scale semantics,
  weights, model graph, NGRAM settings, and scheduler;
- leave every non-M384 GEMM on the installed stock route;
- do not try `1 x 1`, `2 x 2`, another tile, Stream-K, or a second schedule.

Before an endpoint, run one exact real-weight component across each affected
projection family actually reached by target verification. Compare stock and
candidate outputs under the runtime's unchanged oracle and measure repeated
kernel medians. Record the exact GEMM shapes, selected kernel signatures,
cluster/grid geometry, and the minimum launch or occupancy counter needed to
show whether the partial M cluster was removed. Derive a conservative
whole-request bound from the bound trace without treating overlapping summed
kernel time as wall time.

Only an exact component with a credible positive whole-request bound admits
one profiler-off candidate-only c32 endpoint against the persisted stock
control `0.6049806232813353 s/request`. The candidate must produce 32/32
complete rows, exact token IDs, finish reasons and usage, stable cache/server
accounting, and positive service time without p95 regression. Persist
candidate-path audit rows proving the production endpoint selected the M384
`1 x 2 x 1` kernel. Zero audit rows or an ordinary compile/import/path defect
is an invalid integration attempt; use the shared repair handshake and repair
it in the same claim without replaying valid science.

Do not replay the stock control, QLEN endpoint, wave trajectory, quality
suites, 10K view, rolling stream, critical-path trace, or any consumed
component. Run no cluster, tile, draft-depth, concurrency, backend, or
scheduler sweep.

## Decision

Retain the M384 schedule if the exact component and candidate-only endpoint
are both positive with exact serving semantics. Any reproducible positive gain
is useful because it compounds the quality-qualified, steady c32 wave policy,
whose full-wave planning cost is already below the campaign target.

A non-positive exact component, unsupported `1 x 2 x 1` production kernel, or
valid non-positive endpoint closes only this exact M384 cluster orientation.
Preserve the frozen source, real-weight rows, kernel-selection audit,
measurements, endpoint rows, hashes, and typed terminal.

## Resources

- Priority: `7400`
- Researcher profile: `deep`
- Authorized cumulative spend: `$8`
- Bench: retained `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`
- Compute: at most 55 claimed H200-minutes
- Wall clock: complete and release by `2026-07-24T18:50:00Z`
- Storage: at most 10 GiB of new project-local artifacts
- Provider mutation: forbidden

