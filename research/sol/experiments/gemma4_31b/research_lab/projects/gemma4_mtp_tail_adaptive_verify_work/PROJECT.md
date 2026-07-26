# Gemma 4 MTP tail-adaptive target-verification work

## Question

Can one request-local, semantics-preserving policy reduce the target-model work
performed by Frozen-KV MTP on the exact 4,214-prompt/358-output, concurrency-32
Gemma 4 workload enough to reverse the measured MTP regression?

This is not a replay of the closed overlap-only MTP line. That line proved the
current runtime serializes draft and target verification and measured target
verification itself above the whole sustainable-service ceiling. This project
may change proposal depth, per-request continuation, or the decision to enter
target verification, but must preserve the stock target model, target token
semantics, cache ownership, and workload.

## Decision-bearing evidence

Use
`../sglang_v0512_h200_gemma4_mtp_endpoint/MTP_OVERLAP_REOPENING.json`
(SHA-256
`7fe983448c88632d7f036da8d3ad8e23a58b821f7b1a5f2bff79dab9d4c550f6`)
as the compact historical boundary. Its exact consumed endpoint measured:

- control `0.6743258590313417 s/request`;
- MTP `1.2802698384061841 s/request`, a `89.8592%` regression;
- 354 assistant forwards and 354 target-verification events;
- 4,880 accepted drafts;
- `1,830.576429 ms` assistant time and `25,976.945748 ms` target-verify time;
- acceptance `0.70–0.86` at 32 live requests, collapsing to `0.04–0.13` at
  four live requests.

The prior terminal explicitly permits a separately admitted mechanism that
changes target-verify work or proposal economics.

## Work contract

1. Reconstruct the exact pinned proposal, target-verify, seed-selection,
   accepted-prefix, KV/cache, batch-tree, and scheduler path from the named
   artifact and source. Bind the Gemma hybrid-attention geometry and the
   relevant batch/row shapes.
2. Convert the immutable accepted-depth and timing traces into a deterministic
   per-iteration replay. Separate measured time from derived and inferred
   work; do not transfer performance from another runtime or accelerator.
3. Derive the oracle upper bound for request-local disabling or draft-depth
   adaptation. Include the ordinary-decode work reintroduced when MTP is
   disabled and the effect of shrinking live batch size. If the oracle cannot
   beat the same-session control, falsify this mechanism immediately.
4. If the oracle survives, choose exactly one causal policy and trace it
   through the production source to its first target-work consumer. Prefer an
   online statistic already available in request state; do not introduce an
   offline oracle, quality heuristic, flag sweep, or workload-specific request
   table.
5. Produce a content-addressed source patch and deterministic replay test that
   prove target-token semantics, accepted-prefix accounting, padding, request
   ownership, cache lifetime, and graph behavior. Predict one concrete change
   in target-verify rows/calls and one whole-request service-time bound.

## Terminal

Write `MTP_TAIL_ADAPTIVE_VERIFY_RESULT.json` with one typed result:

- `source_complete_verify_work_candidate`: one production-source intervention,
  replay/oracle evidence that it can beat the same-session control, its exact
  target-work reduction, correctness invariants, and the smallest direct H200
  discriminator; or
- `mechanism_falsified`: the oracle, source path, or semantics prove that this
  request-local mechanism cannot reverse the regression.

A positive result prepares a future direct test after director review; it does
not authorize a GPU claim or endpoint request.

## Budgets and stop rules

- Wall clock: 60 minutes.
- Compute: CPU/source/replay only; zero accelerator seconds.
- Provider spend: `$0.00`.
- Storage: at most 2 GiB of new durable artifacts.
- Provider mutation: forbidden.

Do not replay the consumed MTP endpoint, reopen overlap-only execution, change
the target checkpoint, weaken target semantics, run broad quality, or claim
the shared H200.
